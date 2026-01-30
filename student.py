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
        
        # 1. Target Exam Selection (OUTSIDE form to trigger reruns)
        EXAM_SUBJECTS = {
            "UPSC CSE": ["Ancient History", "Medieval History", "Modern History", "Geography", "Polity", "Economy", "Science & Tech", "Environment", "CSAT", "International Relations", "Current Affairs"],
            "CDS": ["Indian History", "Geography", "English", "Mathematics", "General Science", "Current Affairs", "Indian Polity"],
            "NDA": ["Mathematics", "English", "Physics", "Chemistry", "General Science", "History & Freedom Movement", "Geography", "Current Events"],
            "SSC CGL": ["Quantitative Aptitude", "General Intelligence & Reasoning", "English Comprehension", "General Awareness", "Statistics", "General Studies (Finance & Economics)"],
            "SBI PO": ["Quantitative Aptitude", "Reasoning Ability", "English Language", "General/Economy/Banking Awareness", "Computer Aptitude"],
            "IBPS PO": ["Quantitative Aptitude", "Reasoning Ability", "English Language", "General Awareness", "Computer Aptitude"],
            "JEE Main": ["Physics", "Chemistry", "Mathematics"],
            "JEE Advanced": ["Physics", "Chemistry", "Mathematics"],
            "NEET UG": ["Physics", "Chemistry", "Botany", "Zoology"],
            "GATE": ["Engineering Mathematics", "General Aptitude", "Subject Specific (Civil/Mech/CS/EE/etc.)"],
            "MPSC (Rajyaseva)": ["History", "Geography", "Polity", "Economy", "General Science", "Environment", "CSAT"],
            "MPSC Combined": ["General Knowledge", "History", "Geography", "Economy", "Polity", "General Science", "Aptitude & Methods"],
            "Police Bharti": ["General Knowledge", "Mathematics", "Intelligence Test", "Marathi Language"],
            "AFCAT": ["General Awareness", "Verbal Ability in English", "Numerical Ability", "Reasoning & Military Aptitude"],
            "CAT": ["Verbal Ability & Reading Comprehension", "Data Interpretation & Logical Reasoning", "Quantitative Ability"],
            "CLAT": ["English Language", "Current Affairs (including GK)", "Legal Reasoning", "Logical Reasoning", "Quantitative Techniques"],
            "CTET": ["Child Development & Pedagogy", "Language I", "Language II", "Mathematics", "Environmental Studies"],
            "UGC NET": ["Teaching Aptitude", "Research Aptitude", "Reading Comprehension", "Communication", "Mathematical Reasoning", "Logical Reasoning", "Data Interpretation", "ICT", "People & Environment", "Higher Education System"]
        }

        all_exams = sorted(list(EXAM_SUBJECTS.keys())) + ["Other (Type below)"]
        exam_name_selection = st.selectbox("1. Select Target Exam", all_exams, index=all_exams.index("UPSC CSE"))
        
        # Calculate dynamic subjects list based on selection
        if exam_name_selection == "Other (Type below)":
            subjects_list = ["Other (Type below)"]
        else:
            subjects_list = EXAM_SUBJECTS.get(exam_name_selection, ["General Studies"]) + ["Other (Type below)"]

        with st.form("exam_config_form"):
            # Handle "Other" Exam Name Entry
            if exam_name_selection == "Other (Type below)":
                exam_name = st.text_input("Enter Exam Name", placeholder="e.g., KPSC, TNPSC")
            else:
                exam_name = exam_name_selection

            # 2. Subject Selection (Dynamic)
            subject_selection = st.selectbox("2. Select Subject", subjects_list)
            
            if subject_selection == "Other (Type below)":
                subject = st.text_input("Enter Subject Name", placeholder="e.g., Organic Chemistry")
            else:
                subject = subject_selection

            # 3. Rest of the config
            num_questions = st.number_input("Number of Questions", min_value=1, max_value=50, value=10)
            timer_minutes = st.number_input("Timer (Minutes)", min_value=1, max_value=180, value=10)
            language = st.selectbox("Preferred Language", ["English", "Hindi", "Marathi", "Bengali", "Tamil", "Telugu", "Gujarati", "Kannada", "Malayalam", "Punjabi"])
            
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
                                "timer_minutes": timer_minutes,
                                "original_language": language
                            }
                            st.session_state.current_language = language
                            st.session_state.original_questions = questions
                            
                            # Initial translation if not English
                            if language != "English":
                                with st.spinner(f"Translating questions to {language}..."):
                                    st.session_state.exam_questions = generator.translate_questions(questions, language)
                            else:
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
    if not st.session_state.get("exam_completed"):
        if "copy_warnings" not in st.session_state:
            st.session_state.copy_warnings = 0

        # 4. Violation Logger (Isolated Fragment)
        @st.fragment
        def incident_logger():
            # CSS to hide the hidden buttons
            st.markdown("""
                <style>
                div[data-testid="stButton"] button[key^="hidden_"] {
                    display: none;
                }
                </style>
            """, unsafe_allow_html=True)
            
            # Button for Tab Switch (Immediate Submission)
            if st.button("Log Tab Switch", key="hidden_tab_btn"):
                log_proctoring_event({
                    "student_name": st.session_state.username,
                    "event_type": "tab_switch"
                })
                process_submission(violation="Tab switch detected")

            # Button for Copy Violation (3 Warning Limit)
            if st.button("Log Copy Attempt", key="hidden_copy_btn"):
                st.session_state.copy_warnings += 1
                log_proctoring_event({
                    "student_name": st.session_state.username,
                    "event_type": "copy_attempt",
                    "warning_number": st.session_state.copy_warnings
                })
                
                if st.session_state.copy_warnings >= 3:
                    process_submission(violation="Maximum copy violations reached (3/3)")
                else:
                    st.warning(f"⚠️ **WARNING: Copying is prohibited!** ({st.session_state.copy_warnings}/3 warnings)")
                    st.toast(f"Security Alert: Copy attempt detected!")

        incident_logger()

        st.components.v1.html("""
            <script>
            (function() {
                let copyBtn = null;
                let tabBtn = null;

                const showInstantWarning = (msg) => {
                    const div = window.parent.document.createElement('div');
                    div.style.position = 'fixed';
                    div.style.top = '20px';
                    div.style.left = '50%';
                    div.style.transform = 'translateX(-50%)';
                    div.style.backgroundColor = '#ff4b4b';
                    div.style.color = 'white';
                    div.style.padding = '12px 24px';
                    div.style.borderRadius = '8px';
                    div.style.zIndex = '999999';
                    div.style.fontWeight = 'bold';
                    div.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
                    div.style.transition = 'opacity 0.5s';
                    div.innerText = msg;
                    window.parent.document.body.appendChild(div);
                    setTimeout(() => {
                        div.style.opacity = '0';
                        setTimeout(() => div.remove(), 500);
                    }, 3000);
                };

                const findButtons = () => {
                    const buttons = Array.from(window.parent.document.querySelectorAll('button'));
                    copyBtn = buttons.find(b => b.innerText.includes("Log Copy Attempt"));
                    tabBtn = buttons.find(b => b.innerText.includes("Log Tab Switch"));
                    return copyBtn && tabBtn;
                };

                // Fast polling for button discovery (max 5 seconds)
                let attempts = 0;
                const checkInterval = setInterval(() => {
                    attempts++;
                    if (findButtons() || attempts > 50) {
                        clearInterval(checkInterval);
                        if (copyBtn && tabBtn) {
                            setupListeners();
                        }
                    }
                }, 100);

                function setupListeners() {
                    // Visibility Detection (Tab Switch)
                    window.parent.document.addEventListener('visibilitychange', function() {
                        if (window.parent.document.visibilityState === 'hidden') {
                            showInstantWarning("⚠️ Security Violation: Tab Switch Detected!");
                            tabBtn.click();
                        }
                    });

                    // Focus Loss Detection
                    window.parent.onblur = function() {
                        showInstantWarning("⚠️ Security Violation: Window Focus Lost!");
                        tabBtn.click();
                    };

                    // Copy Detection
                    window.parent.document.addEventListener('copy', (e) => {
                        showInstantWarning("⚠️ WARNING: Copying text is strictly prohibited!");
                        copyBtn.click();
                    });

                    // Prevent Right Click
                    window.parent.document.addEventListener('contextmenu', event => event.preventDefault());
                }
            })();
            </script>
        """, height=0)

    # 5. Timer Logic (Using Sidebar Fragment to avoid fading/errors)
    if "start_time" not in st.session_state:
        st.session_state.start_time = time.time()
    
    def process_submission(violation=None):
        if st.session_state.get("exam_completed"):
            return
            
        questions = st.session_state.exam_questions
        responses = st.session_state.get("student_responses", {})
        config = st.session_state.exam_config
        
        score = 0
        for q in questions:
            if responses.get(q['id']) == q['correct_option']:
                score += 1
        
        submission_data = {
            "student_name": st.session_state.username,
            "student_email": st.session_state.student_email,
            "exam_id": "ai_generated_" + config['exam_name'],
            "score": score,
            "total_questions": len(questions),
            "subject": config['subject'],
            "questions_data": questions,
            "user_responses": responses
        }
        
        if violation:
            submission_data["violation"] = violation
            st.session_state.submission_reason = violation

        submit_exam(submission_data)
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
            
            # Proctoring Status in Sidebar
            st.divider()
            st.write("🛡️ **Proctoring Status**")
            st.info("Active: Browser Monitoring")
            st.warning(f"Copy Warnings: {st.session_state.get('copy_warnings', 0)} / 3")
            
            if remaining <= 0:
                st.error("Time is up! Autosubmitting...")
                time.sleep(1) # Give user a moment to see the message
                process_submission()
        
        show_timer()


    if st.session_state.get("exam_completed"):
        if st.session_state.get("submission_reason"):
            st.error(f"⚠️ **Auto-submitted due to violation: {st.session_state.submission_reason}**")
        else:
            st.success("🎉 Exam Submitted Successfully!")
        
        # --- Analytics Section ---
        score = st.session_state.get('last_score', 0)
        total = len(questions)
        percentage = (score / total) * 100
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Final Score", f"{score} / {total}")
        col2.metric("Accuracy", f"{percentage:.1f}%")
        col3.metric("Status", "Pass" if percentage >= 40 else "Needs Improvement")
        
        st.divider()
        st.subheader("📋 Detailed Performance Review")
        
        user_responses = st.session_state.get("student_responses", {})
        
        for i, q in enumerate(questions):
            chosen = user_responses.get(q['id'])
            correct = q['correct_option']
            is_correct = chosen == correct
            
            with st.container(border=True):
                st.write(f"**Question {i+1}:** {q['question_text']}")
                if q.get('appeared_in'):
                    st.caption(f"Source: {q['appeared_in']}")
                
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
        # --- Language Switcher ---
        col1, col2 = st.columns([3, 1])
        with col2:
            current_lang = st.session_state.get("current_language", "English")
            new_lang = st.selectbox(
                "Change Language", 
                ["English", "Hindi", "Marathi", "Bengali", "Tamil", "Telugu", "Gujarati", "Kannada", "Malayalam", "Punjabi"],
                index=["English", "Hindi", "Marathi", "Bengali", "Tamil", "Telugu", "Gujarati", "Kannada", "Malayalam", "Punjabi"].index(current_lang),
                key="lang_switcher"
            )
            
            if new_lang != current_lang:
                with st.spinner("Translating..."):
                    generator = QuestionGenerator()
                    if new_lang == "English":
                        st.session_state.exam_questions = st.session_state.original_questions
                    else:
                        st.session_state.exam_questions = generator.translate_questions(st.session_state.original_questions, new_lang)
                    st.session_state.current_language = new_lang
                    st.rerun()

        st.divider()
        responses = st.session_state.student_responses
        for i, q in enumerate(questions):
            st.write(f"**Q{i+1}: {q['question_text']}**")
            # Display Question Source/Year
            if q.get('appeared_in'):
                st.caption(f"Source: {q['appeared_in']}")
            
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
        
        with st.expander(f"Exam: {subject} | Accuracy: {accuracy:.1f}% | Date: {date.strftime('%d %b %Y') if date else 'N/A'}"):
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
                st.info(f"**Explanation:** {q.get('explanation', 'N/A')}")
