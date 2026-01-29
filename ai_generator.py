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

    def generate_questions(self, subject, exam_name, num_questions):
        prompt = ChatPromptTemplate.from_template(
            """You are an expert examiner for Indian competitive exams. 
            Generate {num_questions} multiple-choice questions (MCQs) strictly from Previous Year Questions (PYQs) of the {exam_name} exam for the subject {subject}.
            
            IMPORTANT: Use LaTeX formatting for all mathematical expressions, equations, formulas, and symbols. Surround them with $ for inline or $$ for block display (e.g., $x^2 + y^2 = r^2$).
            
            CRITICAL: Ensure the output is a VALID JSON list. If you use backslashes for LaTeX (e.g., \frac), you MUST escape them as double backslashes (e.g., \\frac) in the JSON string.
            
            Note: Prefer decimal format for numerical values and percentages (e.g., 0.5 or 50% instead of 1/2) unless a fraction is specifically required by the question context.
            
            Each question must have:
            1. question_text: The actual question.
            2. option_a: First option.
            3. option_b: Second option.
            4. option_c: Third option.
            5. option_d: Fourth option.
            6. correct_option: The letter (A, B, C, or D).
            7. explanation: A one-liner explanation of why the answer is correct.

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
                    "explanation": "..."
                }}
            ]
            
            Return ONLY the raw JSON.
            """
        )

        chain = prompt | self.llm | self.parser
        
        questions = chain.invoke({
            "subject": subject,
            "exam_name": exam_name,
            "num_questions": num_questions
        })
        
        # Simple validation - sometimes invoke returns [] or empty
        if not questions:
            # Try a fallback model name
            fallback_llm = ChatGroq(
                temperature=0.3,
                model_name="llama3-70b-8192", # Reliable fallback
                groq_api_key=os.getenv("GROQ_API_KEY")
            )
            chain = prompt | fallback_llm | self.parser
            questions = chain.invoke({
                "subject": subject,
                "exam_name": exam_name,
                "num_questions": num_questions
            })

        if isinstance(questions, list):
            # Add unique IDs for Streamlit handling
            for i, q in enumerate(questions):
                q['id'] = f"ai_q_{i}"
            return questions
        return []

# Simple test block
if __name__ == "__main__":
    gen = QuestionGenerator()
    qs = gen.generate_questions("Indian Geography", "CDS", 2)
    print(json.dumps(qs, indent=2))
