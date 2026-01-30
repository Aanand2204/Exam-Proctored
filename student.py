import streamlit as st
import time
import pandas as pd
from database import submit_exam, log_proctoring_event, register_user, authenticate_user, get_submissions
from ai_generator import QuestionGenerator

def student_view():
    st.title("Student Portal - Online Exam")

    # 1. Registration/Login
    if "username" not in st.session_state:
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
                        st.session_state.student_name = username # Keep compatibility
                        st.session_state.student_email = "" # Placeholder
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
        return

    st.sidebar.write(f"Logged in as: **{st.session_state.username}**")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    # Sidebar Navigation
    menu = st.sidebar.radio("Navigation", ["Take New Exam", "Exam History"])
    
    if menu == "Exam History":
        show_history()
        return

    st.write(f"Welcome back, **{st.session_state.username}**")

    # 2. Exam Configuration
    if "exam_config" not in st.session_state:
        st.subheader("Configure Your Exam")
        with st.form("exam_config_form"):
            subject = st.text_input("Subject (e.g., Indian Geography, Modern History)", value="Indian Geography")
            exam_name = st.selectbox("Target Exam", ["CDS", "NDA", "UPSC", "SSC CGL", "AFCAT", "JEE", "NEET", "MPSC", "BANK PO"])
            num_questions = st.number_input("Number of Questions", min_value=1, max_value=50, value=10)
            timer_minutes = st.number_input("Timer (Minutes)", min_value=1, max_value=180, value=1)
            
            generate = st.form_submit_button("Generate Exam & Start")
            
            if generate:
                with st.spinner("Generating PYQs using AI... This may take a moment."):
                    try:
                        generator = QuestionGenerator()
                        questions = generator.generate_questions(subject, exam_name, int(num_questions))
                        
                        if questions:
                            st.session_state.exam_config = {
                                "subject": subject,
                                "exam_name": exam_name,
                                "num_questions": num_questions,
                                "timer_minutes": timer_minutes
                            }
                            st.session_state.exam_questions = questions
                            st.session_state.start_time = time.time()
                            st.rerun()
                        else:
                            st.error("AI generated empty output. Please try a different subject or fewer questions.")
                    except Exception as e:
                        st.error(f"❌ AI Generation Error: {str(e)}")
                        if "rate_limit" in str(e).lower():
                            st.warning("You might be hitting Groq's rate limits. Please wait a minute and try again.")
                        elif "api_key" in str(e).lower():
                            st.warning("There seems to be an issue with your GROQ_API_KEY in the .env file.")
        return

    questions = st.session_state.exam_questions
    config = st.session_state.exam_config
    st.sidebar.subheader("Proctoring Active")
    st.sidebar.warning("Do NOT switch tabs. Any suspicious activity will be logged.")

    # 4. Tab Switch Detection (JS Injection with Isolated Logging)
    @st.fragment
    def incident_logger():
        # CSS to hide the hidden button
        st.markdown("""
            <style>
            div[data-testid="stButton"] button[key="hidden_log_btn"] {
                display: none;
            }
            </style>
        """, unsafe_allow_html=True)
        
        if st.button("Log Incident", key="hidden_log_btn"):
            log_proctoring_event({
                "student_name": st.session_state.student_name,
                "event_type": "tab_switch"
            })
            st.toast("Warning: Tab switch detected and logged!")

    incident_logger()

    st.components.v1.html("""
        <script>
        setTimeout(() => {
            const getBtn = () => {
                const buttons = window.parent.document.querySelectorAll('button');
                return Array.from(buttons).find(b => b.innerText.includes("Log Incident"));
            };

            // Visibility Detection
            window.parent.document.addEventListener('visibilitychange', function() {
                if (window.parent.document.visibilityState === 'hidden') {
                    const btn = getBtn();
                    if (btn) btn.click();
                    alert("SECURITY ALERT: Tab switch detected! This incident has been logged.");
                }
            });

            // Focus Loss Detection
            window.parent.onblur = function() {
                const btn = getBtn();
                if (btn) btn.click();
            };
        }, 1500);
        </script>
    """, height=0)

    # 5. Timer Logic (Using Sidebar Fragment to avoid fading/errors)
    if "start_time" not in st.session_state:
        st.session_state.start_time = time.time()
    
    def process_submission():
        if st.session_state.get("exam_completed"):
            return
            
        questions = st.session_state.exam_questions
        responses = st.session_state.get("student_responses", {})
        config = st.session_state.exam_config
        
        score = 0
        for q in questions:
            if responses.get(q['id']) == q['correct_option']:
                score += 1
        
        submit_exam({
            "student_name": st.session_state.username,
            "student_email": st.session_state.student_email,
            "exam_id": "ai_generated_" + config['exam_name'],
            "score": score,
            "total_questions": len(questions),
            "subject": config['subject'],
            "questions_data": questions,
            "user_responses": responses
        })
        st.session_state.last_score = score
        st.session_state.exam_completed = True
        st.rerun()

    with st.sidebar:
        @st.fragment(run_every="1s")
        def show_timer():
            if st.session_state.get("exam_completed"):
                st.write("✅ **Exam Finished**")
                return

            elapsed = time.time() - st.session_state.start_time
            duration = config['timer_minutes'] * 60
            remaining = max(0, int(duration - elapsed))
            mins, secs = divmod(remaining, 60)
            st.metric("Time Remaining", f"{mins:02d}:{secs:02d}")
            
            if remaining <= 0:
                st.error("Time is up! Autosubmitting...")
                time.sleep(1) # Give user a moment to see the message
                process_submission()
        
        show_timer()


    if st.session_state.get("exam_completed"):
        st.success("🎉 Exam Submitted Successfully!")
        
        # --- Analytics Section ---
        score = st.session_state.get('last_score', 0)
        total = len(questions)
        percentage = (score / total) * 100
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Final Score", f"{score} / {total}")
        col2.metric("Accuracy", f"{percentage:.1f}%")
        col3.metric("Status", "Pass" if percentage >= 40 else "Needs Improvement")
        
        # Simple Chart
        df_chart = pd.DataFrame({
            "Result": ["Correct", "Incorrect"],
            "Count": [score, total - score]
        })
        st.bar_chart(df_chart.set_index("Result"))
        
        st.divider()
        st.subheader("📋 Detailed Performance Review")
        
        user_responses = st.session_state.get("student_responses", {})
        
        for i, q in enumerate(questions):
            chosen = user_responses.get(q['id'])
            correct = q['correct_option']
            is_correct = chosen == correct
            
            with st.container(border=True):
                st.write(f"**Question {i+1}:** {q['question_text']}")
                
                # Show all options with highlights
                options = {
                    "A": q['option_a'],
                    "B": q['option_b'],
                    "C": q['option_c'],
                    "D": q['option_d']
                }
                
                for key, val in options.items():
                    label = f"({key}) {val}"
                    if key == correct:
                        st.write(f"✅ **{label} (Correct Answer)**")
                    elif key == chosen:
                        st.write(f"❌ ~~{label} (Your Choice)~~")
                    else:
                        st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;{label}")
                
                # One-liner explanation
                st.info(f"**Explanation:** {q.get('explanation', 'No explanation available.')}")
        
        col1, col2 = st.columns(2)
        if col1.button("📑 Take New Test"):
            # Clear only exam-related state
            keys_to_keep = ["username", "student_name", "student_email"]
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep:
                    del st.session_state[key]
            st.rerun()
            
        if col2.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()
        return

    # 6. Exam Interface
    st.divider()
    
    if "student_responses" not in st.session_state:
        st.session_state.student_responses = {}

    @st.fragment
    def exam_interface():
        responses = st.session_state.student_responses
        for i, q in enumerate(questions):
            st.write(f"**Q{i+1}: {q['question_text']}**")
            # Update responses in session state directly
            choice = st.radio(
                f"Select an option for Q{i+1}:",
                ["A", "B", "C", "D"],
                key=f"q_{q['id']}",
                index=None if q['id'] not in responses else ["A", "B", "C", "D"].index(responses[q['id']]),
                format_func=lambda x: f"{x}) {q[f'option_{x.lower()}']}"
            )
            if choice:
                responses[q['id']] = choice
            st.write("---")
        
        st.divider()
        st.write("### Ready to finish?")
        confirm = st.checkbox("I confirm that I have answered all questions and I am ready to submit.")
        if st.button("Submit Exam", type="primary"):
            if not confirm:
                st.error("Please check the confirmation box before submitting.")
            else:
                process_submission()
    
    exam_interface()

def show_history():
    st.header("Your Exam History")
    submissions = get_submissions(st.session_state.username)
    
    if not submissions:
        st.info("You haven't taken any exams yet.")
        return
    
    for sub in submissions:
        subject = sub.get("subject", "N/A")
        total = sub.get("total_questions", 0)
        score = sub.get("score", 0)
        date = sub.get("submission_time")
        accuracy = (score/total)*100 if total > 0 else 0
        
        with st.expander(f"Exam: {subject} | Accuracy: {accuracy:.1f}% | Date: {date.strftime('%Y-%m-%d %H:%M') if date else 'N/A'}"):
            st.write(f"**Exam Type:** {sub.get('exam_id', 'AI Generated')}")
            st.write(f"**Total Questions:** {total}")
            st.write(f"**Your Score:** {score}")
            st.write(f"**Accuracy:** {(score/total)*100:.1f}%" if total > 0 else "N/A")
            
            if "questions_data" in sub and "user_responses" in sub:
                if st.button("View Detailed Result", key=f"view_{sub['id']}"):
                    st.session_state.selected_exam_history = sub
                    st.rerun()
            else:
                st.warning("Detailed question data is not available for this older record.")
            st.write("---")

    if st.session_state.get("selected_exam_history"):
        sub = st.session_state.selected_exam_history
        st.divider()
        st.subheader(f"Detailed Review: {sub.get('subject')}")
        if st.button("Close Detailed Review"):
            del st.session_state.selected_exam_history
            st.rerun()

        qs = sub['questions_data']
        res = sub['user_responses']
        
        for i, q in enumerate(qs):
            chosen = res.get(q['id'])
            correct = q['correct_option']
            with st.container(border=True):
                st.write(f"**Question {i+1}:** {q['question_text']}")
                options = {"A": q['option_a'], "B": q['option_b'], "C": q['option_c'], "D": q['option_d']}
                for key, val in options.items():
                    label = f"({key}) {val}"
                    if key == correct:
                        st.write(f"✅ **{label} (Correct Answer)**")
                    elif key == chosen:
                        st.write(f"❌ ~~{label} (Your Choice)~~")
                    else:
                        st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;{label}")
                st.info(f"**Explanation:** {q.get('explanation', 'N/A')}")
