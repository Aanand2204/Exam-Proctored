import streamlit as st
import time
import pandas as pd
from database import submit_exam, log_proctoring_event, register_user, authenticate_user, get_submissions
from ai_generator import QuestionGenerator
from constants import EXAM_SUBJECTS, SUPPORTED_LANGUAGES, DIFFICULTY_LEVELS
from proctoring import inject_proctoring_assets, render_proctoring_triggers, reset_proctoring_ui

def student_view():
    st.title("Student Portal - Online Exam")

    # 1. Auth Flow
    if "username" not in st.session_state:
        auth_view()
        return

    # Sidebar Header (Always visible when logged in)
    st.sidebar.write(f"Logged in as: **{st.session_state.username}**")
    
    # 2. Navigation Control
    menu = st.sidebar.radio("Navigation", ["Take New Exam", "Exam History"])
    
    if st.sidebar.button("Logout", key="main_logout"):
        st.session_state.clear()
        st.rerun()

    if menu == "Exam History":
        show_history()
        return

    # 3. Exam State Flow
    if st.session_state.get("exam_completed"):
        results_view(st.session_state.exam_questions)
    elif "exam_config" in st.session_state:
        exam_session_view(st.session_state.exam_questions, st.session_state.exam_config)
    else:
        exam_config_view()

def auth_view():
    """Handles user login and registration."""
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            login_btn = st.form_submit_button("Login")
            if login_btn:
                user = authenticate_user(username, password)
                if user:
                    st.session_state.username = username
                    st.session_state.student_name = username
                    st.session_state.student_email = ""
                    st.success(f"Logged in as {username}")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
    
    with tab2:
        with st.form("register_form"):
            new_user = st.text_input("New Username")
            new_pass = st.text_input("New Password", type="password")
            confirm_pass = st.text_input("Confirm Password", type="password")
            reg_btn = st.form_submit_button("Register")
            if reg_btn:
                if not new_user or not new_pass:
                    st.error("Please fill all fields")
                elif new_pass != confirm_pass:
                    st.error("Passwords do not match")
                else:
                    if register_user(new_user, new_pass):
                        st.success("Registration successful! Please login.")
                    else:
                        st.error("Username already exists")

def exam_config_view():
    """Handles the exam setup and question generation."""
    st.subheader("Configure Your Exam")
    
    all_exams = sorted(list(EXAM_SUBJECTS.keys())) + ["Other (Type below)"]
    exam_name_selection = st.selectbox("1. Select Target Exam", all_exams, index=all_exams.index("UPSC CSE"))
    
    exam_name = st.text_input("Enter Exam Name", placeholder="e.g., KPSC, TNPSC") if exam_name_selection == "Other (Type below)" else exam_name_selection
    subjects_list = ["Other (Type below)"] if exam_name_selection == "Other (Type below)" else EXAM_SUBJECTS.get(exam_name_selection, ["General Studies"]) + ["Other (Type below)"]
    subject_selection = st.selectbox("2. Select Subject", subjects_list)
    subject = st.text_input("Enter Subject Name", placeholder="e.g., Organic Chemistry") if subject_selection == "Other (Type below)" else subject_selection

    with st.form("exam_config_form"):
        num_questions = st.number_input("Number of Questions", min_value=1, max_value=50, value=10, key="cfg_num_qs")
        timer_minutes = st.number_input("Timer (Minutes)", min_value=1, max_value=180, value=10, key="cfg_timer")
        difficulty = st.selectbox("Difficulty Level", DIFFICULTY_LEVELS, index=1, key="cfg_diff")
        language = st.selectbox("Preferred Language", SUPPORTED_LANGUAGES, key="cfg_lang")
        
        if st.form_submit_button("Generate Exam & Start"):
            if not subject or not exam_name:
                st.error("Please fill all fields.")
            else:
                with st.spinner("Generating PYQs using AI..."):
                    try:
                        generator = QuestionGenerator()
                        previous_submissions = get_submissions(st.session_state.username)
                        # Avoid recently generated questions from ALL subjects to ensure maximum diversity across sessions
                        avoid_texts = [q['question_text'] for sub in previous_submissions for q in sub.get('questions_data', [])]
                        
                        # Note: QuestionGenerator.generate_questions will handle truncating this to the last 100
                        questions = generator.generate_questions(subject, exam_name, int(num_questions), difficulty=difficulty, avoid_questions=avoid_texts)
                        if questions:
                            st.session_state.exam_config = {"subject": subject, "exam_name": exam_name, "num_questions": num_questions, "timer_minutes": timer_minutes, "difficulty": difficulty, "original_language": language}
                            st.session_state.current_language = language
                            st.session_state.original_questions = questions
                            st.session_state.current_q_index = 0
                            
                            if language != "English":
                                st.session_state.exam_questions = generator.translate_questions(questions, language)
                            else:
                                st.session_state.exam_questions = questions

                            st.session_state.start_time = time.time()
                            st.rerun()
                        else:
                            st.error("⚠️ AI returned no questions.")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")

def exam_session_view(questions, config):
    """Handles the active exam session."""
    inject_proctoring_assets()
    
    def process_submission(violation=None):
        responses = st.session_state.get("student_responses", {})
        score = sum(1 for q in questions if responses.get(q['id']) == q['correct_option'])
        submission_data = {
            "student_name": st.session_state.username,
            "student_email": st.session_state.get("student_email", ""),
            "exam_id": "ai_generated_" + config['exam_name'],
            "score": score,
            "total_questions": len(questions),
            "subject": config['subject'],
            "questions_data": questions,
            "user_responses": responses,
            "violation": violation
        }
        if violation: st.session_state.submission_reason = violation
        submit_exam(submission_data)
        st.session_state.last_score = score
        st.session_state.exam_completed = True
        reset_proctoring_ui()
        st.rerun()

    render_proctoring_triggers(st.session_state.username, process_submission)

    # UI Components
    col1, col2 = st.columns([3, 1])
    with col2:
        selected_lang = st.selectbox("Language", SUPPORTED_LANGUAGES, index=SUPPORTED_LANGUAGES.index(st.session_state.current_language))
        if selected_lang != st.session_state.current_language:
            st.session_state.exam_questions = QuestionGenerator().translate_questions(st.session_state.original_questions, selected_lang) if selected_lang != "English" else st.session_state.original_questions
            st.session_state.current_language = selected_lang
            st.rerun()

    @st.fragment(run_every="1s")
    def main_timer():
        elapsed = time.time() - st.session_state.start_time
        remaining = max(0, int(config['timer_minutes'] * 60 - elapsed))
        mins, secs = divmod(remaining, 60)
        st.metric("⏳ Time Left", f"{mins:02d}:{secs:02d}")
        if remaining <= 0: process_submission(violation="Time Explored")

    main_timer()

    @st.fragment
    def question_palette():
        responses = st.session_state.get("student_responses", {})
        total = len(questions)
        curr = st.session_state.get("current_q_index", 0)
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total", total)
        m2.metric("Attempted", len(responses))
        m3.metric("Remaining", total - len(responses))

        cols = st.columns(10)
        for i in range(total):
            label = f"{i+1}"
            if i == curr: label = f"📍 {label}"
            elif questions[i]['id'] in responses: label = f"✅ {label}"
            
            if cols[i % 10].button(label, key=f"pal_{i}", use_container_width=True, type="primary" if i == curr else "secondary"):
                st.session_state.current_q_index = i
                st.rerun()

    question_palette()
    st.divider()

    @st.fragment
    def exam_interface():
        idx = st.session_state.get("current_q_index", 0)
        q = questions[idx]
        responses = st.session_state.get("student_responses", {})
        
        if st.session_state.get("show_submit_confirm"):
            with st.container(border=True):
                st.warning("⚠️ **Confirm Submission?**")
                st.write("You have reached the end of the exam. Are you ready to submit your responses?")
                if st.checkbox("I have reviewed my answers and am ready to submit.", key="confirm_check"):
                    if st.button("🚀 Final Submit", type="primary", use_container_width=True):
                        process_submission()
                st.divider()
                if st.button("🔙 Back to Questions", use_container_width=True):
                    del st.session_state.show_submit_confirm
                    st.rerun()
        else:
            st.write(f"**Question {idx + 1} of {len(questions)}**")
            st.progress((idx + 1) / len(questions))
            
            with st.container(border=True):
                st.markdown(f"**Q{idx+1}:**  \n{q['question_text']}")
                choice = st.radio("Options", ["A", "B", "C", "D"], key=f"q_{q['id']}", index=None if q['id'] not in responses else ["A", "B", "C", "D"].index(responses[q['id']]), format_func=lambda x: f"{x}) {q[f'option_{x.lower()}']}")
                if choice: responses[q['id']] = choice
                st.session_state.student_responses = responses

            c1, c2, c3 = st.columns(3)
            if c1.button("⬅️ Previous", disabled=(idx == 0)):
                st.session_state.current_q_index -= 1
                st.rerun()
            if c2.button("Next ➡️") if idx < len(questions) - 1 else False:
                st.session_state.current_q_index += 1
                st.rerun()
            if c3.button("🚀 Submit", type="primary") if idx == len(questions) - 1 else False:
                st.session_state.show_submit_confirm = True
                st.rerun()

    exam_interface()

def results_view(questions):
    """Displays exam results with detailed question review."""
    st.header("Exam Results")
    if st.session_state.get("submission_reason"):
        st.error(f"⚠️ **Auto-submitted due to violation: {st.session_state.submission_reason}**")
    else:
        st.success(f"🎉 Exam Submitted Successfully! Score: {st.session_state.get('last_score', 0)} / {len(questions)}")
    
    score = st.session_state.get('last_score', 0)
    total = len(questions)
    percentage = (score / total) * 100
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Final Score", f"{score} / {total}")
    col2.metric("Accuracy", f"{percentage:.1f}%")
    col3.metric("Status", "Pass" if percentage >= 40 else "Needs Improvement")
    
    st.divider()
    st.subheader("📋 Detailed Performance Review")
    
    res = st.session_state.get("student_responses", {})
    for i, q in enumerate(questions):
        chosen = res.get(q['id'])
        correct = q['correct_option']
        
        with st.container(border=True):
            st.markdown(f"**Question {i+1}:**  \n{q['question_text']}")
            if q.get('appeared_in'):
                st.caption(f"Source: {q['appeared_in']}")
            
            options = {"A": q['option_a'], "B": q['option_b'], "C": q['option_c'], "D": q['option_d']}
            for key, val in options.items():
                label = f"({key}) {val}"
                if key == correct:
                    st.write(f"✅ **{label} (Correct Answer)**")
                elif key == chosen:
                    st.write(f"❌ ~~{label} (Your Choice)~~")
                else:
                    st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;{label}")
            
            st.info(f"**Explanation:**\n\n{q.get('explanation', 'No explanation available.')}")
    
    col1, col2 = st.columns(2)
    if col1.button("📑 Take New Test", key="new_test_btn"):
        keys_to_keep = ["username", "student_name", "student_email"]
        for key in list(st.session_state.keys()):
            if key not in keys_to_keep:
                del st.session_state[key]
        st.rerun()
        
    if col2.button("🚪 Logout", key="logout_btn_res"):
        st.session_state.clear()
        st.rerun()

def show_history():
    st.header("History")
    for sub in get_submissions(st.session_state.username):
        with st.expander(f"{sub.get('subject')} - {sub.get('score')}/{sub.get('total_questions')}"):
            st.write(f"Date: {sub.get('submission_time')}")
