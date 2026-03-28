import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import re
import requests
import time
from datetime import datetime

# --- 1. CẤU HÌNH GIAO DIỆN & CSS (TINH GỌN & CHỮ TO MOBILE) ---
st.set_page_config(page_title="Dank's class management", layout="wide")

st.markdown("""
    <style>
    .big-font { font-size:70px !important; font-weight: bold; text-align: center; }
    div.stButton > button { height: 100px; font-size: 25px !important; font-weight: bold; border-radius: 20px; }
    .context-display {
        font-family: 'Times New Roman', serif;
        font-size: 22px !important; line-height: 1.8;
        white-space: pre-wrap !important; background-color: #ffffff;
        padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 15px; color: #333;
    }
    .correct-ans { color: #28a745; font-weight: bold; }
    .wrong-ans { color: #dc3545; font-weight: bold; }
    audio { width: 100%; margin-bottom: 20px; border-radius: 10px; background-color: #f1f3f4; }

    @media (max-width: 768px) {
        .context-display { font-size: 18px !important; }
        .stMarkdown p, .stRadio label { font-size: 18px !important; }
        div.stButton > button { height: 60px; font-size: 18px !important; margin-bottom: 10px; }
    }

    /* Vô hiệu hoá menu chuột phải/nhấn giữ trên ảnh */
    img {
        -webkit-touch-callout: none !important;
        -webkit-user-select: none !important;
        user-select: none !important;
        pointer-events: none;
        border-radius: 8px;
    }
    </style>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    """, unsafe_allow_html=True)

# --- 2. HÀM HỖ TRỢ ---

def get_drive_url(url):
    if not url or not isinstance(url, str): return ""
    match = re.search(r'(?:d/|id=)([a-zA-Z0-9_-]{25,})', url)
    if match: return f'https://drive.google.com/uc?export=download&id={match.group(1)}'
    return url.strip()

@st.cache_data(show_spinner=False)
def get_drive_content(url):
    try:
        direct_url = get_drive_url(url)
        response = requests.get(direct_url, timeout=15)
        if response.status_code == 200: return response.content
    except: return None
    return None

def display_drive_image(url):
    content = get_drive_content(url)
    if content: st.image(content, use_container_width=True)

def display_drive_audio(url):
    content = get_drive_content(url)
    if content: st.audio(content)

def clean_nan(val):
    if pd.isna(val) or str(val).lower() == "nan" or str(val).strip() == "": return " " 
    return str(val).strip()

# --- 3. KHỞI TẠO FIREBASE ---
if not firebase_admin._apps:
    if "firebase" in st.secrets:
        fb_dict = dict(st.secrets["firebase"])
        if "private_key" in fb_dict: fb_dict["private_key"] = fb_dict["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(fb_dict)
    else:
        cred = credentials.Certificate('data/serviceAccountKey.json')
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- 4. QUẢN LÝ SESSION ---
if 'user' not in st.session_state: st.session_state.user = None
if 'view_mode' not in st.session_state: st.session_state.view_mode = 'list'
if 'current_df' not in st.session_state: st.session_state.current_df = None
if 'selected_ex' not in st.session_state: st.session_state.selected_ex = None
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}

def logout():
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.rerun()

# CALLBACK LÀM BÀI
def start_lesson_callback(ex, ex_id):
    try:
        df = pd.read_excel(get_drive_url(ex['excel_link']))
        df.columns = [str(c).strip().lower() for c in df.columns]
        st.session_state.current_df, st.session_state.current_ex_info = df, ex
        st.session_state.current_ex_id, st.session_state.view_mode = ex_id, 'quiz'
        st.session_state.user_answers = {}
    except: st.error("Lỗi nạp bài.")

# CALLBACK XEM LẠI ĐÁP ÁN TRỰC TIẾP
def start_review_direct_callback(ex, history):
    try:
        df = pd.read_excel(get_drive_url(ex['excel_link']))
        df.columns = [str(c).strip().lower() for c in df.columns]
        st.session_state.current_df = df
        latest_sub = max(history, key=lambda x: x['submitted_at'])
        # Chuyển keys từ string sang int để khớp với vòng lặp review
        st.session_state.user_answers = {int(k): v for k, v in latest_sub.get('user_answers', {}).items()}
        st.session_state.view_mode = 'review'
    except: st.error("Lỗi nạp dữ liệu Review.")

# --- 5. CÁC TRANG ---

def login_page():
    st.markdown('<h1 style="text-align: center;">🔑 Đăng nhập Hệ thống</h1>', unsafe_allow_html=True)
    with st.container(border=True):
        email = st.text_input("📧 Tài khoản của bạn:")
        password = st.text_input("🔒 Mật khẩu:", type="password")
        if st.button("Xác nhận", use_container_width=True):
            user_ref = db.collection('users').document(email).get()
            if user_ref.exists:
                user_data = user_ref.to_dict()
                if str(user_data.get('password')) == password:
                    st.session_state.user = {**user_data, 'email': email}
                    st.rerun()
                else: st.error("Sai mật khẩu.")
            else: st.error("Email không tồn tại.")

def teacher_page():
    st.sidebar.button("Đăng xuất", on_click=logout)
    st.title("👨‍🏫 Quản lý Học viên")
    tab_assign, tab_manage, tab_stats = st.tabs(["📤 Giao bài", "👥 Quản lý", "📊 Thống kê"])

    with tab_assign:
        with st.expander("Giao bài tập mới", expanded=True):
            students = [s.id for s in db.collection('users').where('role', '==', 'student').stream()]
            title = st.text_input("Tiêu đề")
            ex_type = st.selectbox("Loại", ["Reading (Part 5,6,7)", "Listening", "Vocab Game"])
            link = st.text_input("Link Excel")
            assigned = st.multiselect("Giao cho:", students)
            if st.button("🚀 Đăng bài", use_container_width=True):
                db.collection('exercises').add({'title': title, 'type': ex_type, 'excel_link': link, 'assigned_to': assigned, 'created_at': firestore.SERVER_TIMESTAMP, 'review_permissions': {e: False for e in assigned}})
                st.success("Đã đăng!")

    with tab_manage:
        all_students = [s.id for s in db.collection('users').where('role', '==', 'student').stream()]
        selected_st = st.selectbox("Chọn học sinh:", ["-- Chọn --"] + all_students)
        if selected_st != "-- Chọn --":
            exs = db.collection('exercises').where('assigned_to', 'array_contains', selected_st).stream()
            for doc in exs:
                ex, ex_id = doc.to_dict(), doc.id
                with st.expander(f"📝 {ex['title']}"):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"Loại: {ex['type']}")
                    perms = ex.get('review_permissions', {})
                    if c2.toggle("Cho phép Review", value=perms.get(selected_st, False), key=f"rev_{ex_id}_{selected_st}"):
                        perms[selected_st] = True
                        db.collection('exercises').document(ex_id).update({'review_permissions': perms})
                    else:
                        perms[selected_st] = False
                        db.collection('exercises').document(ex_id).update({'review_permissions': perms})
                    if c3.button("🗑️ Xoá bài", key=f"del_{ex_id}_{selected_st}"):
                        new_a = [e for e in ex['assigned_to'] if e != selected_st]
                        if not new_a: db.collection('exercises').document(ex_id).delete()
                        else: db.collection('exercises').document(ex_id).update({'assigned_to': new_a})
                        st.rerun()

    with tab_stats:
        chosen_students = st.multiselect("Chọn nhóm học sinh:", all_students)
        if chosen_students:
            student_ex_lists = []
            for email in chosen_students:
                exs = db.collection('exercises').where('assigned_to', 'array_contains', email).stream()
                student_ex_lists.append({doc.to_dict()['title'] for doc in exs})
            common_titles = list(set.intersection(*student_ex_lists)) if student_ex_lists else []
            if common_titles:
                selected_ex_title = st.selectbox("Chọn bài tập:", ["-- Chọn bài tập --"] + common_titles)
                if selected_ex_title != "-- Chọn bài tập --":
                    ex_doc = db.collection('exercises').where('title', '==', selected_ex_title).limit(1).get()[0]
                    df_exam = pd.read_excel(get_drive_url(ex_doc.to_dict()['excel_link']))
                    df_exam.columns = [str(c).strip().lower() for c in df_exam.columns]
                    all_subs = db.collection('submissions').where('exercise_title', '==', selected_ex_title).stream()
                    student_data_map = {email: [] for email in chosen_students}
                    for s in all_subs:
                        d = s.to_dict()
                        if d['student_email'] in chosen_students:
                            try:
                                n, t = map(int, d.get('score_raw', '0/0').split('/'))
                                d['score_percent'] = (n / t) * 100
                            except: d['score_percent'] = 0
                            student_data_map[d['student_email']].append(d)
                    summary_list, wrong_stats = [], {i: set() for i in range(len(df_exam))}
                    for email in chosen_students:
                        subs = student_data_map[email]
                        if subs:
                            percents = [s['score_percent'] for s in subs]
                            summary_list.append({'Học sinh': email, 'Thấp nhất (%)': min(percents), 'Cao nhất (%)': max(percents)})
                            latest = max(subs, key=lambda x: x['submitted_at'])
                            ans_dict = latest.get('user_answers', {})
                            for i, row in df_exam.iterrows():
                                ck = str(row.get('correct_ans', '')).strip().upper()
                                mapping = {clean_nan(row.get('opt_a')):'A', clean_nan(row.get('opt_b')):'B', clean_nan(row.get('opt_c')):'C', clean_nan(row.get('opt_d')):'D'}
                                if mapping.get(ans_dict.get(str(i))) != ck: wrong_stats[i].add(email)
                    if summary_list:
                        df_summary = pd.DataFrame(summary_list)
                        st.markdown("#### 📊 So sánh sự tiến bộ (%)")
                        c_low, c_high = st.columns(2)
                        c_low.write("**📉 Lần thấp nhất**")
                        c_low.bar_chart(df_summary.set_index('Học sinh')['Thấp nhất (%)'])
                        c_high.write("**🏆 Lần cao nhất**")
                        c_high.bar_chart(df_summary.set_index('Học sinh')['Cao nhất (%)'])
                        st.markdown("#### 🎯 Phân tích chi tiết lỗi sai")
                        c_l, c_r = st.columns([1, 1])
                        q_errs = [(i, len(emails)) for i, emails in wrong_stats.items() if len(emails) > 0]
                        q_errs.sort(key=lambda x: x[1], reverse=True)
                        with c_l:
                            sel_q = st.radio("Chọn câu:", [f"Câu {i+1} ({cnt} bạn sai)" for i, cnt in q_errs], label_visibility="collapsed")
                            idx = int(sel_q.split(" ")[1]) - 1
                        with c_r:
                            row = df_exam.iloc[idx]
                            with st.container(border=True):
                                if clean_nan(row.get('audio')) != " ": display_drive_audio(row.get('audio'))
                                ctx = clean_nan(row.get('context'))
                                for p in ctx.split(";;"):
                                    if p.strip().startswith("http"): display_drive_image(p.strip())
                                    else: st.markdown(f"*{p.strip()}*")
                                st.markdown(f"**Câu {idx+1}: {clean_nan(row.get('question'))}**")
                                ck = str(row.get('correct_ans')).strip().upper()
                                st.success(f"✅ Đáp án: {ck}. {clean_nan(row.get(f'opt_{ck.lower()}'))}")
                                st.error(f"❌ Các bạn đang sai: {', '.join(wrong_stats[idx])}")

def student_page():
    st.sidebar.button("Đăng xuất", on_click=logout)
    u_email = st.session_state.user['email']
    st.title(f"👋 Xin chào, {st.session_state.user.get('full_name', 'Học viên')}!")
    st.divider()

    if st.session_state.view_mode == 'list':
        st.subheader("📚 Bài tập của bạn")
        all_subs = [s.to_dict() for s in db.collection('submissions').where('student_email', '==', u_email).stream()]
        exs = db.collection('exercises').where('assigned_to', 'array_contains', u_email).stream()
        for doc in exs:
            ex, ex_id = doc.to_dict(), doc.id
            history = [s for s in all_subs if s.get('exercise_title') == ex['title']]
            can_review = ex.get('review_permissions', {}).get(u_email, False)
            
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.subheader(f"{ex['type']} - {ex['title']}")
                    if history:
                        scores = [int(s.get('score_raw','0/0').split('/')[0]) for s in history]
                        raws = [s.get('score_raw') for s in history]
                        st.markdown(f"🔢 Lần làm: `{len(history)}` | 📉 Thấp: `{raws[scores.index(min(scores))]}` | 🏆 Cao: `{raws[scores.index(max(scores))]}`")
                    else: st.markdown("🆕 *Chưa làm*")
                
                with c2:
                    st.button("Làm bài ➔", key=f"btn_{ex_id}", on_click=start_lesson_callback, args=(ex, ex_id), use_container_width=True)
                    # NÚT REVIEW HIỆN DƯỚI NẾU ĐỦ ĐIỀU KIỆN
                    if history and can_review:
                        st.button("Xem lại 🧐", key=f"rev_btn_{ex_id}", on_click=start_review_direct_callback, args=(ex, history), use_container_width=True)

    elif st.session_state.view_mode == 'quiz':
        st.subheader(f"✍️ {st.session_state.current_ex_info['title']}")
        if st.button("⬅ Thoát"): st.session_state.view_mode = 'list'; st.rerun()
        with st.form("quiz_form"):
            df, answers = st.session_state.current_df, {}
            df['group'] = (df['context'] != df['context'].shift()).cumsum()
            for _, group_df in df.groupby('group'):
                first = group_df.iloc[0]
                if 'audio' in df.columns and pd.notna(first.get('audio')):
                    display_drive_audio(str(first.get('audio')))
                ctx = clean_nan(first.get('context'))
                if ctx.lower() in [" ", "nan", "none"]:
                    for i, r in group_df.iterrows():
                        st.write(f"**Câu {i+1}: {clean_nan(r.get('question','Listen'))}**")
                        opts = [clean_nan(r.get('opt_a')), clean_nan(r.get('opt_b')), clean_nan(r.get('opt_c'))]
                        if clean_nan(r.get('opt_d')).upper() != "NONE" and clean_nan(r.get('opt_d')) != " ": opts.append(clean_nan(r.get('opt_d')))
                        answers[i] = st.radio(f"q{i}", opts, key=f"q{i}", index=None, label_visibility="collapsed"); st.divider()
                else:
                    st.markdown("---")
                    l_col, r_col = st.columns([1, 1])
                    with l_col:
                        with st.container(height=650):
                            for p in ctx.split(";;"):
                                if p.strip().startswith("http"): display_drive_image(p.strip())
                                else: st.markdown(f'<div class="context-display">{p.strip()}</div>', unsafe_allow_html=True)
                    with r_col:
                        with st.container(height=650):
                            for i, r in group_df.iterrows():
                                st.write(f"**Câu {i+1}: {clean_nan(r.get('question'))}**")
                                opts = [clean_nan(r.get('opt_a')), clean_nan(r.get('opt_b')), clean_nan(r.get('opt_c'))]
                                if clean_nan(r.get('opt_d')).upper() != "NONE" and clean_nan(r.get('opt_d')) != " ": opts.append(clean_nan(r.get('opt_d')))
                                answers[i] = st.radio(f"q{i}", opts, key=f"q{i}", index=None, label_visibility="collapsed"); st.write("---")
            if st.form_submit_button("Nộp bài 🏁", use_container_width=True):
                correct = sum(1 for i, r in df.iterrows() if {clean_nan(r.get('opt_a')):'A', clean_nan(r.get('opt_b')):'B', clean_nan(r.get('opt_c')):'C', clean_nan(r.get('opt_d')):'D'}.get(answers.get(i)) == str(r.get('correct_ans','')).strip().upper())
                st.session_state.user_answers, st.session_state.res = answers, f"{correct}/{len(df)}"
                db.collection('submissions').add({'student_email':u_email, 'exercise_title':st.session_state.current_ex_info['title'], 'score_raw':st.session_state.res, 'user_answers': {str(k): v for k, v in answers.items()}, 'submitted_at':datetime.now()})
                st.session_state.view_mode = 'res'; st.rerun()

    elif st.session_state.view_mode == 'res':
        st.balloons(); st.title(f"🎉 Kết quả: {st.session_state.res}")
        if st.button("XEM LẠI ĐÁP ÁN (REVIEW)"): st.session_state.view_mode = 'review'; st.rerun()
        if st.button("QUAY LẠI TRANG CHỦ"): st.session_state.view_mode = 'list'; st.rerun()

    elif st.session_state.view_mode == 'review':
        st.title("🧐 Review đáp án"); df = st.session_state.current_df
        for i, r in df.iterrows():
            st.write(f"**Câu {i+1}: {r.get('question')}**")
            u_ans = st.session_state.user_answers.get(i)
            ck = str(r.get('correct_ans')).strip().upper()
            ct = clean_nan(r.get(f'opt_{ck.lower()}'))
            if {clean_nan(r.get('opt_a')):'A', clean_nan(r.get('opt_b')):'B', clean_nan(r.get('opt_c')):'C', clean_nan(r.get('opt_d')):'D'}.get(u_ans) == ck:
                st.markdown(f"✅ Đúng: **{u_ans}**")
            else: st.markdown(f"❌ Chọn: {u_ans} | 👉 Đúng: <span class='correct-ans'>{ct}</span>", unsafe_allow_html=True)
            st.divider()
        if st.button("XONG"): st.session_state.view_mode = 'list'; st.rerun()

# --- 6. ĐIỀU HƯỚNG ---
if st.session_state.user is None: login_page()
else: teacher_page() if st.session_state.user.get('role') == 'teacher' else student_page()
