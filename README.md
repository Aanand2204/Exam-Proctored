# AI-Powered Proctored Exam System

A modern, dynamic exam system built with Streamlit, Groq (Llama 3.3), and LangChain. It generates high-quality MCQs from Previous Year Questions (PYQs) for competitive exams like CDS, NDA, and UPSC.

## 🚀 Features

- **AI Question Generation**: On-the-fly generation of MCQs based on subject and target exam.
- **Mathematical Support**: Full LaTeX rendering for complex formulas and equations.
- **Student Authentication**: Secure login and registration with hashed passwords.
- **Exam Analytics**: Instant score breakdown, accuracy metrics, and visual performance charts.
- **Exam History**: Detailed review of past attempts, including questions, user answers, and AI-generated explanations.
- **Proctoring**: Basic tab-switch detection and logging to ensure exam integrity.

## 🛠️ Tech Stack

- **Frontend**: Streamlit
- **AI/LLM**: Groq (Llama 3.3 via LangChain)
- **Database**: MongoDB (Atlas)
- **Formatting**: LaTeX (via KaTeX/Streamlit)

## 📦 Setup & Installation

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd <repo-name>
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   MONGO_URI=your_mongodb_atlas_uri
   DB_NAME=proctor_exam_db
   GROQ_API_KEY=your_groq_api_key
   ```

4. **Run the Application**:
   ```bash
   streamlit run app.py
   ```

## 🌐 Deployment

This app is ready for deployment on **Streamlit Cloud**:
1. Connect your GitHub repository to Streamlit Cloud.
2. Add your `.env` variables (MONGO_URI, GROQ_API_KEY, etc.) to the **Secrets** section of your Streamlit app settings.
3. Deploy!

