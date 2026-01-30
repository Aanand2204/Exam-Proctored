import os
import json
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from dotenv import load_dotenv

load_dotenv()

class QuestionGenerator:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or api_key == "your_groq_api_key_here":
            raise ValueError("GROQ_API_KEY not found or not set in .env file.")
        
        self.llm = ChatGroq(
            temperature=0.3,
            model_name="llama-3.3-70b-versatile",
            groq_api_key=api_key
        )
        self.parser = JsonOutputParser()

    def _clean_latex(self, text):
        """Standardizes LaTeX escaping and ensures it is wrapped in $ if not already."""
        if not isinstance(text, str):
            return text
        
        # Convert literal \\ to \ if it looks like LaTeX
        # (LLMs often over-escape in JSON output)
        cleaned = text.replace("\\\\", "\\")
        
        # Remove common phonetic LaTeX marks that AI sometimes uses for Indian scripts
        # patterns like: \bar{ā}, \bar{s}, \bar s, \bar a, etc.
        import re
        
        # Pass 1: Handle braced patterns: \bar{a} -> a
        cleaned = re.sub(r'\\(bar|acute|grave|ddot|hat|tilde|check|breve|dot|vec)\{([^}]*)\}', r'\2', cleaned)
        
        # Pass 2: Handle unbraced patterns: \bar a -> a (but only for single characters to avoid breaking math)
        # We only do this for characters often found in phonetic romanization
        cleaned = re.sub(r'\\(bar|acute|grave|ddot|hat|tilde|check|breve|dot|vec)\s+([a-zA-Z])', r'\2', cleaned)
        
        # Pass 3: Specifically target the user's reported error cases
        cleaned = cleaned.replace("\\bar{ā}", "ā")
        cleaned = cleaned.replace("\\bar{s}", "s")
        cleaned = cleaned.replace("\\bar{ū}", "ū")
        
        return cleaned

    def generate_questions(self, subject, exam_name, num_questions):
        prompt = ChatPromptTemplate.from_template(
            """You are an expert examiner for Indian competitive exams. 
            Generate {num_questions} multiple-choice questions (MCQs) strictly from Previous Year Questions (PYQs) of the {exam_name} exam for the subject {subject}.
            
            IMPORTANT: Use LaTeX formatting for ALL mathematical expressions, equations, formulas, and symbols. 
            ALWAYS surround them with $ for inline (e.g., $x^2$) or $$ for block display.
            
            CRITICAL: Ensure the output is a VALID JSON list. In the JSON string, backslashes MUST be escaped (e.g., "\\\\frac").
            
            Each question must have:
            1. question_text: The actual question. (MUST be unique within this set, no repetitions)
            2. option_a: First option.
            3. option_b: Second option.
            4. option_c: Third option.
            5. option_d: Fourth option.
            6. correct_option: The letter (A, B, C, or D).
            7. explanation: A one-liner explanation of why the answer is correct.
            8. appeared_in: A string stating when and where this question was asked (e.g., "CDS 2022" or "SSC CGL 2021 Tier I").

            STRICT REQUIREMENTS:
            - SUBJECT RELEVANCE: Every single question must be directly and strictly related to the subject: {subject}. Do not include questions from other subjects or topics.
            - SOURCE ADHERENCE: You MUST ONLY generate questions that have actually appeared in previous years of the {exam_name} exam. Do not invent new questions.
            - METADATA: Every question MUST specify exactly which year and paper it appeared in via the 'appeared_in' field.
            - NO REPETITION: Every question in the list must be distinct.
            - UNIQUE OPTIONS: All four options (A, B, C, D) for a given question MUST be different from each other.

            Format the output strictly as a JSON list of objects.
            Example:
            [
                {{
                    "question_text": "...",
                    "option_a": "...",
                    "option_b": "...",
                    "option_c": "...",
                    "option_d": "...",
                    "correct_option": "A",
                    "explanation": "...",
                    "appeared_in": "CDS 2021"
                }}
            ]
            
            Return ONLY the raw JSON.
            """
        )

        chain = prompt | self.llm | self.parser
        
        try:
            questions = chain.invoke({
                "subject": subject,
                "exam_name": exam_name,
                "num_questions": num_questions
            })
        except Exception:
            questions = []
        
        # Simple validation - sometimes invoke returns [] or empty
        if not questions:
            # Try a fallback model name
            fallback_llm = ChatGroq(
                temperature=0.3,
                model_name="llama3-70b-8192", # Reliable fallback
                groq_api_key=os.getenv("GROQ_API_KEY")
            )
            chain = prompt | fallback_llm | self.parser
            try:
                questions = chain.invoke({
                    "subject": subject,
                    "exam_name": exam_name,
                    "num_questions": num_questions
                })
            except Exception:
                questions = []

        if isinstance(questions, list):
            # Clean and add unique IDs
            for i, q in enumerate(questions):
                q['id'] = f"ai_q_{i}"
                for key in ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'explanation']:
                    if key in q:
                        q[key] = self._clean_latex(q[key])
            return questions
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
    qs = gen.generate_questions("Indian Geography", "CDS", 2)
    print(json.dumps(qs, indent=2))
