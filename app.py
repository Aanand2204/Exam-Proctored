import streamlit as st
from student import student_view

st.set_page_config(page_title="Proctored Exam System", layout="wide")

def main():
    student_view()

if __name__ == "__main__":
    main()
