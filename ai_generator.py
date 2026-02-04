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

    def _clean_explanation(self, text):
        """Detects and removes repetitive loops/stuttering in AI explanations."""
        if not isinstance(text, str):
            return text
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        unique_lines = []
        seen_content = set()
        
        for line in lines:
            # Strip the step number (e.g., "1. ") for comparison
            content = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            # If we see identical content twice or if it's too short to be unique, skip sequential duplicates
            if content in seen_content:
                continue
            
            unique_lines.append(line)
            seen_content.add(content)
            
            # Hard cap at 15 steps to prevent infinite hallucinations
            if len(unique_lines) >= 15:
                unique_lines.append("... (Step-wise solution continues)")
                break
                
        # Re-number the steps if we cleaned them
        final_lines = []
        for i, line in enumerate(unique_lines):
            content = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            if content == "... (Step-wise solution continues)":
                final_lines.append(content)
            else:
                final_lines.append(f"{i+1}. {content}")
                
        return '\n'.join(final_lines)

    def generate_questions(self, subject, exam_name, num_questions, difficulty="Medium", avoid_questions=None):
        import datetime
        current_date = datetime.date.today().strftime("%B %Y")
        
        avoid_context = ""
        if avoid_questions:
            # Avoid the 50 most recent questions to prevent repetitive patterns
            avoid_list = "\n".join([f"- {q}" for q in avoid_questions[-50:]])
            avoid_context = f"\nCRITICAL: AVOID THESE RECENTLY GENERATED QUESTIONS (DO NOT REPEAT TOPIC OR TEXT):\n{avoid_list}\n"

        prompt_template = """You are an expert examiner for Indian competitive exams (like UPSC, SSC, CDS, NDA, etc.). 
            Today's Date: {current_date}
            
            Generate {num_questions} multiple-choice questions (MCQs) for the {exam_name} exam for the subject {subject}.
            DIFFICULTY LEVEL: {difficulty}
            
            STRICT ADHERENCE TO EXAM STANDARD:
            - You are a senior paper setter for the '{exam_name}' exam. Your reputation depends on the accuracy and difficulty of these questions.
            - {exam_name} LEVEL TARGET:
                * UPSC CSE: Graduate/Post-graduate level analytical depth. MUST use multi-statement questions (Statement 1, Statement 2, etc.) for at least 50% of the set. Focus on complex inter-disciplinary links.
                * AFCAT/SSC/CDS: Under-graduate level concepts. Focus on logical precision, speed-based tricks, and conceptual "traps" in wording.
            - DIFFICULTY DEFINITION:
                * Easy: Single-fact questions or direct 1-step logic.
                * Medium: Requires linking 2 facts, eliminating 2 distractors, or 2-step logical deduction.
                * Hard: MUST require complex analysis. For UPSC, this means identifying the correct combination of 3-4 statements. For AFCAT, this means complex spatial/verbal logic or tricky multi-step numeric reasoning (if subject is Numerical Ability).
            
            INTERNAL VERIFICATION (CHAIN OF THOUGHT):
            - BEFORE writing the JSON for each question, you MUST mentally solve it yourself.
            - Ensure the 'correct_option' you provide is logically bulletproof.
            - If the subject is 'Logical Reasoning' or contains 'Intelligence'/'Aptitude':
                * Check for "Syllogism" validity (All A are B, some B are C...).
                * Verify "Blood Relation" trees manually.
                * Ensure "Coding-Decoding" patterns are consistent across the entire question.
                * Do NOT choose an option as correct if it is only "partially" true.
            
            STRICT REQUIREMENTS:
            - REPETITION IS STRICTLY FORBIDDEN: Do NOT generate questions similar to the 'AVOID' list. If you repeat a topic or text, the test is invalid.
            - STATEMENT-BASED QUESTIONS: If you generate a question with statements (1, 2, 3...), you MUST include the full text of those statements within 'question_text'. Use DOUBLE NEWLINES (\n\n) after the intro text and after EACH statement so they are printed line by line.
            - The questions MUST feel indistinguishable from an ACTUAL official question paper of {exam_name}.
            
            CRITICAL: 
            - Ensure the output is a VALID JSON list. In the JSON string, backslashes MUST be escaped (e.g., "\\\\frac").
            - The 'explanation' MUST justify WHY the correct option is right and WHY the others are wrong (concisely).
            
            Each question must have:
            1. question_text: The actual question. (STRICT: Do NOT include formulas, hints, or the method of solving in the question text. The student must use their own knowledge. Formulas belong ONLY in the explanation).
            2. option_a: First option. (STRICT: ONLY provide the content. DO NOT include the label '(a)' or 'A.' or 'a)').
            3. option_b: Second option. (STRICT: DO NOT include labels).
            4. option_c: Third option. (STRICT: DO NOT include labels).
            5. option_d: Fourth option. (STRICT: DO NOT include labels).
            6. correct_option: The letter (A, B, C, or D).
            7. explanation: Subject-specific format:
                - For 'Mathematics', 'Physics', 'Chemistry': A clear, direct STEP-BY-STEP solution using numbered steps (1., 2., etc.). 
                  CRITICAL: PROVIDE ONLY THE CALCULATION. NO "Thinking out loud". JUST THE FACTS.
                - For ALL OTHER subjects (History, Geography, Reasoning, etc.): A single, concise ONE-LINE explanation that PROVES the correct answer.
            8. appeared_in: A string stating when and where this question was asked (e.g., "CDS 2022").
               - For 'Current Affairs', if it's a very recent event not yet in a specific exam paper, state "Latest Current Affairs (Month Year)".

            STRICT REQUIREMENTS:
            - QUESTION COUNT: You MUST generate EXACTLY {num_questions} questions.
            - SUBJECT RELEVANCE: Every single question must be directly related to the subject: {subject}. 
              WARNING: If the subject is History, DO NOT ask math questions. If it is Current Affairs, DO NOT ask about historical events from years ago.
            - DIVERSITY: Every question must be distinct from the 'PREVIOUSLY GENERATED QUESTIONS' list provided above.
            - SOURCE: Focus on real PYQs for static subjects. For Current Affairs, focus on the latest news. NEVER return an empty list.
            - METADATA: Every question MUST specify source in 'appeared_in'.
            - NO REPETITION: Every question in the list must be distinct.
            - UNIQUE OPTIONS: All four options (A, B, C, D) MUST be different.

            {avoid_context}

            SUBJECT-SPECIFIC GUIDANCE:
            - If the subject is 'Current Affairs', generate questions ONLY on high-impact national and international events, awards, appointments, sports, and schemes from the LAST 6 MONTHS (Relative to {current_date}). Do NOT ask previous year questions for Current Affairs.
            - If the subject is 'History', 'Polity', 'Geography', or 'Economics', focus on factual, analytical, and descriptive questions. Do NOT use mathematical formulas or complex calculations unless it's a specific numerical date or statistic.
            - If the subject is 'Mathematics', 'Physics', or 'Chemistry', use LaTeX for ALL mathematical expressions, equations, formulas, and symbols.
            - If the subject name contains 'Reasoning', 'Intelligence', or 'Aptitude' (except 'Quantitative Aptitude' or 'Numerical Ability'), generate STRICTLY logical reasoning questions (verbal or non-verbal logic). DO NOT include mathematical calculations, number system problems, or any questions requiring arithmetic formulas. Focus on patterns, syllogisms, blood relations, directions, coding-decoding, etc.
            - ALWAYS surround LaTeX with $ for inline (e.g., $x^2$) or $$ for block display.

            Format the output strictly as a JSON list of objects.
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
                max_tokens=4096 
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

        questions = None
        for model in models:
            logger.info(f"Trying model: {model}...")
            questions = attempt_generation_with_retry(model, {
                "subject": subject,
                "exam_name": exam_name,
                "num_questions": num_questions,
                "difficulty": difficulty,
                "current_date": current_date,
                "avoid_context": avoid_context
            })
            if questions:
                break
        
        if isinstance(questions, list) and len(questions) > 0:
            # Clean and add unique IDs
            for i, q in enumerate(questions):
                q['id'] = f"ai_q_{i}"
                for key in ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'explanation']:
                    if key in q:
                        q[key] = self._clean_latex(q[key])
                        # Extra cleaning for explanations to prevent loops and hallucinations
                        if key == 'explanation':
                            q[key] = self._clean_explanation(q[key])
                        # Extra strip for options to prevent double labeling
                        if key.startswith('option_'):
                            q[key] = self._strip_option_label(q[key])
            return questions
        
        logger.error("Final result: Empty list returned.")
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
