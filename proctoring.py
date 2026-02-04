import streamlit as st
import streamlit.components.v1 as components
from database import log_proctoring_event

def inject_proctoring_assets():
    """Injects CSS and JS for proctoring into the Streamlit app components."""
    components.html("""
        <script>
        (function() {
            // 1. Inject Global CSS into Parent Head
            let style = window.parent.document.getElementById('proctor-styles');
            if (!style) {
                style = window.parent.document.createElement('style');
                style.id = 'proctor-styles';
                window.parent.document.head.appendChild(style);
            }
            style.innerHTML = `
                /* Hide Proctoring Buttons */
                div[id*="proctor-trigger-container"],
                button:has(div:contains("Trigger")),
                [data-testid="stBaseButton-secondary"]:has(span:contains("Trigger")),
                button[key="proc_tab"],
                button[key="proc_copy"] {
                    display: none !important;
                    visibility: hidden !important;
                    height: 0 !important;
                    width: 0 !important;
                    position: absolute !important;
                    opacity: 0 !important;
                }
                
                /* Hide Sidebar Navigation during test */
                [data-testid="stSidebarNav"],
                [data-testid="stSidebarNavItems"],
                .st-emotion-cache-1kyx97a {
                    display: none !important;
                }
            `;

            const showInstantWarning = (msg) => {
                const div = window.parent.document.createElement('div');
                div.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#ff4b4b;color:white;padding:12px 24px;border-radius:8px;z-index:999999;font-weight:bold;box-shadow:0 4px 12px rgba(0,0,0,0.3);';
                div.innerText = msg;
                window.parent.document.body.appendChild(div);
                setTimeout(() => div.remove(), 4000);
            };

            const findButtons = () => {
                const allButtons = Array.from(window.parent.document.querySelectorAll('button'));
                const tabBtn = allButtons.find(b => b.innerText.toLowerCase().includes("trigger tab switch"));
                const copyBtn = allButtons.find(b => b.innerText.toLowerCase().includes("trigger copy warning"));
                return { tabBtn, copyBtn };
            };

            const setupListeners = () => {
                if (window.parent.__proctoring_v3) return;
                window.parent.__proctoring_v3 = true;

                window.parent.document.addEventListener('visibilitychange', () => {
                    if (window.parent.document.visibilityState === 'hidden') {
                        const { tabBtn } = findButtons();
                        if (tabBtn) {
                            showInstantWarning("⚠️ Security Violation: Tab Switch Detected!");
                            tabBtn.click();
                        }
                    }
                });

                window.parent.addEventListener('blur', () => {
                    const { tabBtn } = findButtons();
                    if (tabBtn) {
                        showInstantWarning("⚠️ Security Violation: Focus Loss Detected!");
                        tabBtn.click();
                    }
                });

                const handleCopyAttempt = (type) => {
                    const { copyBtn } = findButtons();
                    if (copyBtn) {
                        showInstantWarning(`⚠️ WARNING: ${type} is strictly prohibited!`);
                        copyBtn.click();
                    }
                };

                window.parent.document.addEventListener('copy', () => handleCopyAttempt("Copying"));
                window.parent.document.addEventListener('paste', () => handleCopyAttempt("Pasting"));
                window.parent.document.addEventListener('cut', () => handleCopyAttempt("Cutting"));
                window.parent.document.addEventListener('contextmenu', e => e.preventDefault());
            };

            let attempts = 0;
            const interval = setInterval(() => {
                attempts++;
                const { tabBtn, copyBtn } = findButtons();
                if (tabBtn && copyBtn) {
                    clearInterval(interval);
                    setupListeners();
                } else if (attempts > 200) { clearInterval(interval); }
            }, 50);
        })();
        </script>
        <div id="proctor-trigger-container" style="display:none"></div>
    """, height=0)

def render_proctoring_triggers(username, process_submission_callback):
    """Renders the invisible buttons that bridge JS events to Streamlit state."""
    if st.button("Trigger Tab Switch", key="proc_tab"):
        log_proctoring_event({"student_name": username, "event_type": "tab_switch"})
        process_submission_callback(violation="Tab switch detected")

    if st.button("Trigger Copy Warning", key="proc_copy"):
        st.session_state.copy_warnings = st.session_state.get('copy_warnings', 0) + 1
        log_proctoring_event({
            "student_name": username,
            "event_type": "copy_attempt",
            "warning_number": st.session_state.copy_warnings
        })
        if st.session_state.copy_warnings >= 3:
            process_submission_callback(violation="Maximum copy violations reached (3/3)")
        else:
            st.warning(f"⚠️ **Security Alert: Copying is prohibited!** ({st.session_state.copy_warnings}/3)")
            st.toast("Copy attempt detected!")

def reset_proctoring_ui():
    """Resets the proctoring UI elements in the parent window."""
    components.html("""
        <script>
        const style = window.parent.document.getElementById('proctor-styles');
        if (style) style.innerHTML = ''; 
        window.parent.__proctoring_v3 = false;
        </script>
    """, height=0)
