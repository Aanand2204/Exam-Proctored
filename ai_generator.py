import os
import json
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from dotenv import load_dotenv

import re
import logging

load_dotenv()

# Configure logging to file
logging.basicConfig(
    filename='exam_system_debug.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class QuestionGenerator:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or api_key == "your_groq_api_key_here":
            raise ValueError("GROQ_API_KEY not found or not set in .env file.")
        
        self.llm = ChatGroq(
            temperature=0.2, # Lowered for stricter instruction following (avoiding repeats, following rubric)
            model_name="llama-3.3-70b-versatile",
            groq_api_key=api_key
        )
        self.parser = JsonOutputParser()

    def _clean_latex(self, text):
        """Standardizes LaTeX escaping and ensures it is wrapped in $ if not already."""
        if not isinstance(text, str):
            return text
        
        # Protect backslashes for Streamlit's markdown/LaTeX engine
        # We want to ensure that \frac remains as \frac and doesn't get 
        # interpreted as a form-feed (\f) by Streamlit.
        cleaned = text
        
        # Remove common phonetic LaTeX marks for Indian scripts
        import re
        cleaned = re.sub(r'\\(bar|acute|grave|ddot|hat|tilde|check|breve|dot|vec)\{([^}]*)\}', r'\2', cleaned)
        cleaned = re.sub(r'\\(bar|acute|grave|ddot|hat|tilde|check|breve|dot|vec)\s+([a-zA-Z])', r'\2', cleaned)
        
        # If the text contains known LaTeX commands but NO '$', wrap it
        latex_keywords = [
            r'\\frac', r'\\sqrt', r'\\alpha', r'\\beta', r'\\gamma', r'\\delta', 
            r'\\theta', r'\\pi', r'\\infty', r'\^', r'_\{', r'\\right', r'\\left',
            r'\\sum', r'\\log', r'\\sin', r'\\cos', r'\\tan', r'\\int', r'\\circ'
        ]
        if any(re.search(kw, cleaned) for kw in latex_keywords) and '$' not in cleaned:
            cleaned = f"${cleaned}$"

        # Fix the issue where AI wraps plain text in '$' including spaces
        def math_cleanup(match):
            inner = match.group(1)
            # If it's just plain text (mostly letters and spaces), strip the $
            if re.match(r'^[a-zA-Z0-9\s.,%₹/\\]+$', inner) and not re.search(r'[\^_{}\\]', inner):
                return inner
            return f"${inner}$"
            
        cleaned = re.sub(r'\$([^$]+)\$', math_cleanup, cleaned)
        
        # Specifically target the user's reported error cases for phonetic marks
        cleaned = cleaned.replace("\\bar{ā}", "ā")
        cleaned = cleaned.replace("\\bar{s}", "s")
        cleaned = cleaned.replace("\\bar{ū}", "ū")
        
        return cleaned

    def _strip_option_label(self, text):
        """Strips leading labels like (a), A., a) from the option text."""
        if not isinstance(text, str):
            return text
        import re
        # Strip letters like "(a) ", "A. ", "a) "
        # We require a separator (. or )) OR a trailing space to avoid mangling words like "Aditya"
        text = re.sub(r'^\(?[a-dA-D]\)?[\.\)]\s*', '', text)
        # If no separator, only strip if it's a single letter followed by space
        text = re.sub(r'^[a-dA-D]\s+', '', text)
        
        # Strip digit labels like "1. ", "1) "
        text = re.sub(r'^[1-4][\.\)]\s*', '', text)
        return text.strip()

    def _strip_conversational_filler(self, text):
        """Removes meta-commentary while preserving analytical context."""
        if not isinstance(text, str):
            return text
            
        # 1. Remove obvious conversational preamble only if it precedes purely meta-talk
        filler_patterns = [
            r"^(Here is|This question|The solution|Explanation):\s*",
            r"^(Note|Tip|Hint):\s*.*$",
            r"^Step-by-step:\s*",
            r"^\(.*?\) " 
        ]
        
        cleaned = text
        for pattern in filler_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
            
        # Instead of stripping "Based on...", we'll let the prompt guide the AI 
        # to produce crisp steps, as regex is too blunt for semantic filtering.
            
        lines = cleaned.split('\n')
        final_lines = []
        for line in lines:
            line = line.strip()
            if not line: continue
            if "matches option" in line.lower() and line != lines[-1]:
                continue
            final_lines.append(line)
            
        return '\n'.join(final_lines)

    def _clean_explanation(self, text):
        """Detects and removes repetitive loops/stuttering and strips conversational filler."""
        if not text:
            return ""
            
        # Handle cases where LLM returns a list instead of a string
        if isinstance(text, list):
            text = "\n".join([str(t) for t in text])
            
        if not isinstance(text, str):
            text = str(text)
        
        # 1. Normalize formatting: Ensure numbered steps are on new lines if they are glued together
        # e.g., "1. First step. 2. Second step." -> "1. First step.\n2. Second step."
        text = re.sub(r'(?<=\.)\s+(\d+[\.\)])\s+', r'\n\1 ', text)
        
        # 2. Ban speculative trailing content (heuristic)
        text = re.sub(r'(Assuming|Perhaps|Maybe|Likely|It might be|Another pattern).*$', '', text, flags=re.IGNORECASE | re.MULTILINE)

        # Strip conversational filler first
        cleaned_text = self._strip_conversational_filler(text)
        
        lines = [line.strip() for line in cleaned_text.split('\n') if line.strip()]
        unique_lines = []
        seen_content = set()
        
        for line in lines:
            # Strip formatting for comparison to detect loops
            content = re.sub(r'^\d+[\.\)]\s*', '', line).strip().lower()
            if content in seen_content or len(content) < 3:
                continue
            
            # Additional constraint: No paragraphs. If a line is too long, truncate it
            if len(line.split()) > 60: 
                line = ' '.join(line.split()[:60]) + "..."
                
            unique_lines.append(line)
            seen_content.add(content)
            
            if len(unique_lines) >= 10: # Cap at 10 steps for crispness
                break
                
        final_lines = []
        for i, line in enumerate(unique_lines):
            content = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            final_lines.append(f"{i+1}. {content}")
                
        return '\n'.join(final_lines)

    def generate_questions(self, subject, exam_name, num_questions, difficulty="Medium", avoid_questions=None):
        import datetime
        current_date = datetime.date.today().strftime("%B %Y")
        
        avoid_context = ""
        if avoid_questions:
            # Compress avoid list to just unique prefixes to save prompt space
            avoid_list = "\n".join([f"- {q[:60]}..." for q in set(avoid_questions[-100:])])
            avoid_context = f"\nCRITICAL: AVOID THESE RECENT TOPICS (TEXT PREFIXES):\n{avoid_list}\n"

        prompt_template = """You are a senior paper setter for the '{exam_name}' exam. 
            
            CRITICAL: GENERATE EXACTLY {num_questions} MCQs. 
            ONLY RETURN THE JSON LIST. No preamble.
            
            Subject: {subject}
            Difficulty: {difficulty}
            Target Count: {num_questions}
            
            DIFFICULTY BENCHMARKS (STRICT ADHERENCE):
            * EASY (Avoid these if difficulty is 'Hard'):
                - Single-step logic (e.g., "Find 10% of 500").
                - Direct lookup (e.g., "Who founded the Maurya Empire?").
                - Simple mapping (e.g., "L=12, find O").
            * HARD (Mandatory if difficulty is 'Hard'):
                - Multi-step logic (At least 3-4 steps).
                - Inter-disciplinary (e.g., "Link a 19th-century economic policy to a specific modern law").
                - Complexity (e.g., "Math: Compound interest vs Simple interest with partial withdrawals").
                - Reasoning: Complex blood relations with 4 generations and indirect titles.
            
            VARIETY & REPETITION RULES:
            - UNIVERSAL DIVERSITY MANDATE: EVERY question in this set MUST cover a completely different sub-topic within '{subject}'.
            - SUB-TOPIC SHUFFLE: If Subject is Math, do NOT give 2 Algebra questions. Give (1) Geometry, (2) Speed, (3) Probability, etc.
            - {avoid_context}
            
            PHASE 1: DIVERSITY & LOGIC AUDIT
            1. List {num_questions} distinct sub-topics you will use.
            2. Solve each mentally to ensure it matches the chosen option.
            
            PHASE 2: JSON GENERATION
            Ensure output is VALID JSON.
            
            STRICT REQUIREMENTS:
            - QUESTION COUNT: You MUST generate EXACTLY {num_questions} questions.
            - SUBJECT RELEVANCE: Every single question must be directly related to the subject: {subject}. 
            - NO SPECULATION: Phrases like 'Assuming', 'Perhaps', 'Maybe', or 'Another pattern' are STRICTLY FORBIDDEN. Every step must be factual.
            - LOGICAL CERTAINTY: Every explanation MUST lead to a definitive conclusion that matches the correct_option. NO TRAILING CONTENT. Ensure every sequence is finished.
            - SUBJECT-SPECIFIC GUIDANCE:
                * If the subject is 'Current Affairs', generate questions ONLY on events from the LAST 6 MONTHS (Relative to {current_date}).
                * If Math/Physics/Science, use LaTeX ($...$ or $$...$$). NEVER use "Statement 1, 2" format.
                * If Reasoning (except Quant), focus on Patterns, Syllogisms, Blood Relations.
            
            Each question MUST have:
            1. question_text: The complete question. (Math: NO statements).
            2. option_a/b/c/d: Four distinct options.
            3. correct_option: A, B, C, or D.
            4. explanation: Substantive, numbered steps. NO filler. Every step must be a complete sentence.
            5. appeared_in: Real exam source.
            """
        prompt = ChatPromptTemplate.from_template(prompt_template)

        # Use current supported high-availability models
        models = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "meta-llama/llama-4-scout-17b-16e-instruct"
        ]
        
        def attempt_generation_with_retry(model_name, params, retries=1):
            import time
            import re
            
            def _repair_json(bad_json_str):
                """Attempts to fix common LLM JSON errors, including truncation and unclosed quotes."""
                fixed = bad_json_str.strip()
                
                # 1. Surgical Backslash Protection
                # Only double backslashes that are NOT followed by characters that should be escaped in JSON (", \, /, b, f, n, r, t, u)
                # This prevents breaking \" (escaped quote) while fixing \frac (missing backslash for JSON)
                
                def bslash_rep(m):
                    bs = m.group(1)
                    char = m.group(2)
                    # If it's already a valid JSON escape sequence, leave it
                    if char in '"\\/bfnrtu':
                        return bs + char
                    # Otherwise, it might be a LaTeX command like \frac -> needs to be \\frac for JSON
                    return bs + bs + char

                fixed = re.sub(r'(\\+)(.)', bslash_rep, fixed)

                # 2. Handle unclosed quotes (aware of escaped quotes)
                quote_count = len(re.findall(r'(?<!\\)"', fixed))
                if quote_count % 2 != 0:
                    fixed += '"'

                # 3. Handle truncation: Close objects and the main list
                if not fixed.endswith(']'):
                    opens = fixed.count('{')
                    closes = fixed.count('}')
                    if opens > closes:
                        fixed += '}' * (opens - closes)
                    if not fixed.endswith(']'):
                        fixed += ']'
                
                return fixed

            def _extract_json(content):
                """Extracts JSON block from response, handling markdown code blocks."""
                # Try finding JSON in markdown blocks first
                md_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                if md_match:
                    return md_match.group(1)
                
                # Fallback: Greedy from first [ to last ]
                start = content.find('[')
                end = content.rfind(']')
                if start != -1 and end != -1:
                    return content[start:end+1]
                
                return content

            current_llm = ChatGroq(
                temperature=0.2,
                model_name=model_name,
                groq_api_key=os.getenv("GROQ_API_KEY"),
                max_tokens=8000 
            )
            current_chain = prompt | current_llm
            
            for attempt in range(retries + 1):
                try:
                    response = current_chain.invoke(params)
                    content = response.content if hasattr(response, 'content') else str(response)
                    
                    json_str = _extract_json(content)
                    
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError as je:
                        logger.warning(f"Initial JSON parse failed for {model_name}: {je}. Attempting repair...")
                        try:
                            repaired = _repair_json(json_str)
                            return json.loads(repaired)
                        except Exception as e:
                            logger.error(f"Repair failed for {model_name}: {e}")
                            
                            # Last ditch: Find all { ... } blocks.
                            # We use a balanced brace approach since LaTeX uses braces too
                            try:
                                valid_qs = []
                                current_pos = 0
                                while True:
                                    s_idx = json_str.find('{', current_pos)
                                    if s_idx == -1: break
                                    
                                    # Find matching closure
                                    brace_lvl = 0
                                    e_idx = -1
                                    for i in range(s_idx, len(json_str)):
                                        if json_str[i] == '{': brace_lvl += 1
                                        elif json_str[i] == '}': 
                                            brace_lvl -= 1
                                            if brace_lvl == 0:
                                                e_idx = i
                                                break
                                    
                                    if e_idx != -1:
                                        obj_str = json_str[s_idx:e_idx+1]
                                        try:
                                            # Still need to repair the small block
                                            rep_obj = _repair_json(obj_str)
                                            valid_qs.append(json.loads(rep_obj))
                                        except: pass
                                        current_pos = e_idx + 1
                                    else:
                                        break
                                if valid_qs: return valid_qs
                            except: pass
                            
                except Exception as e:
                    error_msg = str(e).lower()
                    if "429" in error_msg:
                        wait_time = (attempt + 1) * 3
                        logger.info(f"Rate limit hit on {model_name}. Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    logger.error(f"Generation on {model_name} failed: {e}", exc_info=True)
                    # If it's a critical error (like API key or quota) that isn't a 429, don't just 'break' quietly
                    if any(x in error_msg for x in ["api_key", "quota", "invalid_request"]):
                        raise e 
                    break
            return None

        def _is_too_similar(q_text, gathered_questions):
            """Simple keyword overlap check to prevent same-topic questions."""
            if not gathered_questions: return False
            words_new = set(re.findall(r'\w+', q_text.lower()))
            if len(words_new) < 5: return False # Skip for very short ones
            
            for gq in gathered_questions:
                words_old = set(re.findall(r'\w+', gq['question_text'].lower()))
                overlap = len(words_new.intersection(words_old)) / max(len(words_new), 1)
                if overlap > 0.45: # 45% overlap is usually the same sub-topic or formula
                    return True
            return False

        gathered_questions = []
        max_total_attempts = 3
        total_attempts = 0
        
        # Ensure avoid_questions is a list to prevent NoneType errors
        if avoid_questions is None:
            avoid_questions = []
        
        while len(gathered_questions) < num_questions and total_attempts < max_total_attempts:
            total_attempts += 1
            needed = num_questions - len(gathered_questions)
            
            # Update avoid_context with what we just gathered to prevent intra-batch repetition
            current_avoid_list = list(set(avoid_questions + [q['question_text'] for q in gathered_questions]))
            avoid_list_str = "\n".join([f"- {q[:60]}..." for q in current_avoid_list[-100:]])
            local_avoid_context = f"\nCRITICAL: AVOID THESE RECENT TOPICS (TEXT PREFIXES):\n{avoid_list_str}\n"

            for model in models:
                logger.info(f"Attempting to gather {needed} questions using {model} (Attempt {total_attempts})...")
                new_qs = attempt_generation_with_retry(model, {
                    "subject": subject,
                    "exam_name": exam_name,
                    "num_questions": needed,
                    "difficulty": difficulty,
                    "current_date": current_date,
                    "avoid_context": local_avoid_context
                })
                
                if new_qs and isinstance(new_qs, list):
                    for q in new_qs:
                        if len(gathered_questions) >= num_questions: break
                        if not _is_too_similar(q['question_text'], gathered_questions):
                            gathered_questions.append(q)
                        else:
                            logger.info(f"Rejected similar question: {q['question_text'][:50]}...")
                    
                    if len(gathered_questions) >= num_questions:
                        break
            
            if len(gathered_questions) >= num_questions:
                break

        if gathered_questions:
            # Clean and add unique IDs
            final_qs = gathered_questions[:num_questions]
            for i, q in enumerate(final_qs):
                q['id'] = f"ai_q_{i}"
                for key in ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'explanation']:
                    if key in q:
                        q[key] = self._clean_latex(q[key])
                        if key == 'explanation':
                            q[key] = self._clean_explanation(q[key])
                        if key.startswith('option_'):
                            q[key] = self._strip_option_label(q[key])
                        if key == 'question_text':
                            q[key] = q[key].replace('\\n', '\n').replace('\n', '  \n')
            return final_qs
        
        logger.error("Final result: Failed to gather any valid questions.")
        return []

    def translate_questions(self, questions, target_language):
        """Translates a list of questions into the target language using LLM."""
        if not target_language or target_language.lower() == "english":
            return questions

        prompt = ChatPromptTemplate.from_template(
            """You are a professional translator specializing in academic and competitive exam content.
            Translate the following list of multiple-choice questions into {target_language}.
            
            IMPORTANT: 
            1. Translate everything EXCEPT LaTeX formulas/expressions (e.g., $E=mc^2$). Keep LaTeX EXACTLY as is, including tags like $ or $$.
            2. CRITICAL: NEVER use LaTeX markers like \bar{{}}, \acute{{}}, or \bar{{s}} for phonetic romanization or Indian language terms. Write the words in their natural local script (Hindi, Marathi, etc.) or plain English.
            3. Maintain the EXACT same JSON structure.
            4. Ensure the 'correct_option' field remains (A, B, C, or D).
            5. Translate 'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'explanation', and 'appeared_in'.
            
            Questions to translate:
            {questions_json}
            
            Return ONLY the translated raw JSON.
            """
        )

        chain = prompt | self.llm | self.parser
        
        try:
            translated_questions = chain.invoke({
                "target_language": target_language,
                "questions_json": json.dumps(questions, ensure_ascii=False)
            })
            
            if isinstance(translated_questions, list):
                # Clean LaTeX in translated content
                for q in translated_questions:
                    for key in ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'explanation']:
                        if key in q:
                            q[key] = self._clean_latex(q[key])
                return translated_questions
        except Exception as e:
            print(f"Translation Error: {e}")
            
        return questions

# Simple test block
if __name__ == "__main__":
    gen = QuestionGenerator()
    qs = gen.generate_questions("Current Affairs", "General Studies", 2)
    print(json.dumps(qs, indent=2, ensure_ascii=False))
