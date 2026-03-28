import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import re
import random
import requests
import time
from datetime import datetime

# --- 1. CẤU HÌNH GIAO DIỆN & CSS (TỐI ƯU MOBILE & XOÁ ZOOM LỖI) ---
st.set_page_config(page_title="English Master Pro", layout="wide")

st.markdown("""
    <style>
    /* CSS CHUNG */
    .big-font { font-size:70px !important; font-weight: bold; text-align: center; }
    div.stButton > button { height: 100px; font-size: 30px !important; font-weight: bold; border-radius: 20px; }
    .context-display {
        font-family: 'Times New Roman', serif;
        font-size: 20px !important; line-height: 1.8;
        white-space: pre-wrap !important; background-color: #ffffff;
        padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 15px; color: #333;
    }
    .correct-ans { color: #28a745; font-weight: bold; }
    .wrong-ans { color: #dc3545; font-weight: bold; }
    audio { width: 100%; margin-bottom: 20px; border-radius: 10px; background-color: #f1f3f4; }
    
    /* CSS CHO PHẦN POPUP XEM ẢNH TO */
    [data-testid="stDialog"] div[role="dialog"] {
        width: 95vw !important;
        max-width: 95vw !important;
    }

    /* CSS TỐI ƯU CHO MOBILE */
    @media (max-width: 768px) {
        h1 { font-size: 28px !important; }
        h2 { font-size: 24px !important; }
        h3 { font-size: 20px !important; }
        .context-display { font-size: 18px !important; padding: 10px; }
        .stMarkdown p, .stRadio label { font-size: 18px !important; }
        div.stButton > button { height: 60px; font-size: 18px !important; }
    }
    </style>
    
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    """, unsafe_allow_html=True)

# --- 2. HÀM HỖ TRỢ TOÀN CỤC ---

def get_drive_url(url):
    if not url or not isinstance(url, str): return ""
    match = re.search(r'(?:d/|id=)([a-zA-Z0-9_-]{25,})', url)
    if match:
        return f'https://drive.google.com/uc?export=download&id={match.group(1)}'
    return url.strip()

@st.cache_data(show_spinner=False)
def get_drive_content(url):
    try:
        direct_url = get_drive_url(url)
        response = requests.get(direct_url, timeout=15)
        if response.status_code == 200: return response.content
    except: return None
    return None

# HÀM POPUP XEM ẢNH TO (DÙNG ST.DIALOG)
@st.dialog("Phóng to hình ảnh", width="large")
def image_viewer_dialog(content, caption=""):
    st.image(content, caption=caption, use_container_width=True)

# HÀM HIỂN THỊ ẢNH CÓ NÚT ZOOM (FIX LỖI NHẤN GIỮ)
def display_drive_image(url, caption=""):
    content = get_drive_content(url)
    if content:
        # 1. Hiện ảnh nhỏ bình thường
        st.image(content, caption=caption, use_container_width="auto")
        
        # 2. Tạo nút Zoom riêng ngay dưới ảnh
        c1, c2 = st.columns([4, 1])
        with c2:
            # Dùng key duy nhất cho mỗi nút dựa trên mã băm của URL
            if st.button("🔍 Phóng to", key=f"zoom_{hash(url)}", help="Nhấn để xem ảnh to toàn màn hình"):
                image_viewer_dialog(content, caption)
    else:
        st.warning("Không thể tải ảnh từ Drive.")

def display_drive_audio(url):
    content = get_drive_content(url)
    if content: st.audio(content)
    else: st.warning("Không thể tải âm thanh từ Drive.")

def clean_nan(val):
    if pd.isna(val) or str(val).lower() == "nan" or str(val).strip() == "": return " " 
    return str(val).strip()

# --- 3. KHỞI TẠO FIREBASE (ĐẢM BẢO db TOÀN CỤC) ---
if not firebase_admin._apps:
    if "firebase" in st.secrets:
        fb_dict = dict(st.secrets["firebase"])
        if "private_key" in fb_dict:
            fb_dict["private_key"] = fb_dict["private_key"].replace("\\n", "\n")
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

# CALLBACK SỬA LỖI NHẤN 2 LẦN
def start_lesson_callback(ex, ex_id):
    try:
        url = get_drive_url(ex['excel_link'])
        df = pd.read_excel(url)
        df.columns = [str(c).strip().lower() for c in df.columns]
        st.session_state.current_df = df
        st.session_state.current_ex_info = ex
        st.session_state.current_ex_id = ex_id 
        st.session_state.view_mode = 'quiz'
        st.session_state.user_answers = {} # Reset đáp án cũ
    except Exception as e:
        st.error(f"Lỗi nạp bài: {e}")

# --- 5. CÁC TRANG CHỨC NĂNG ---

# TRANG LOGIN (Đã thêm ô mật khẩu)
def login_page():
    st.markdown('<h1 style="text-align: center;">🔑 Đăng nhập</h1>', unsafe_allow_html=True)
    with st.container(border=True):
        email = st.text_input("📧 Email của bạn:")
        password = st.text_input("🔒 Mật khẩu:", type="password")
        if st.button("Xác nhận", use_container_width=True):
            user_ref = db.collection('users').document(email).get()
            if user_ref.exists:
                user_data = user_ref.to_dict()
                if str(user_data.get('password')) == password:
                    st.session_state.user = {**user_data, 'email': email}
                    st.success("Đăng nhập thành công!")
                    st.rerun()
                else: st.error("Mật khẩu không đúng.")
            else: st.error("Email không tồn tại.")

# TRANG GIÁO VIÊN (GIỮ NGUYÊN MẬT KHẨU & DASHBOARD)
def teacher_page():
    st.sidebar.button("Đăng xuất", on_click=logout)
    st.title("👨‍🏫 Quản lý Giáo viên")
    tab_assign, tab_manage, tab_stats = st.tabs(["📤 Giao bài", "👥 Quản lý Học viên", "📊 Dashboard Thống kê"])

    with tab_assign:
        with st.expander("Giao bài tập mới", expanded=True):
            students = [s.id for s in db.collection('users').where('role', '==', 'student').stream()]
            title = st.text_input("Tiêu đề bài tập")
            ex_type = st.selectbox("Loại", ["Reading (Part 5,6,7)", "Listening", "Vocab Game"])
            link = st.text_input("Link Excel (Drive)")
            assigned = st.multiselect("Giao cho học sinh:", students)
            if st.button("🚀 Đăng bài", use_container_width=True):
                if title and link and assigned:
                    db.collection('exercises').add({
                        'title': title, 'type': ex_type, 'excel_link': link, 
                        'assigned_to': assigned, 'created_at': firestore.SERVER_TIMESTAMP,
                        'review_permissions': {email: False for email in assigned}
                    })
                    st.success("Đã giao bài thành công!")

    with tab_manage:
        all_students = [s.id for s in db.collection('users').where('role', '==', 'student').stream()]
        selected_st = st.selectbox("Chọn học sinh để quản lý:", ["-- Chọn học sinh --"] + all_students)
        if selected_st != "-- Chọn học sinh --":
            st.markdown(f"### Các bài tập của `{selected_st}`")
            student_exs = db.collection('exercises').where('assigned_to', 'array_contains', selected_st).stream()
            for doc in student_exs:
                ex_data, ex_id = doc.to_dict(), doc.id
                with st.expander(f"📝 {ex_data['title']} ({ex_data['type']})"):
                    c_info, c_del = st.columns([3, 1])
                    c_info.write(f"Giao ngày: {ex_data.get('created_at', 'N/A')}")
                    with c_del:
                        if st.button("🗑️ Xóa", key=f"del_{ex_id}_{selected_st}"):
                            new_as = [e for e in ex_data['assigned_to'] if e != selected_st]
                            if not new_as: db.collection('exercises').document(ex_id).delete()
                            else: db.collection('exercises').document(ex_id).update({'assigned_to': new_as})
                            st.rerun()

    with tab_stats:
        st.subheader("📈 Dashboard Phân tích Lớp học")
        chosen_students = st.multiselect("1. Chọn nhóm học sinh:", all_students)
        if chosen_students:
            student_ex_lists = []
            for email in chosen_students:
                exs = db.collection('exercises').where('assigned_to', 'array_contains', email).stream()
                student_ex_lists.append({doc.to_dict()['title'] for doc in exs})
            common_titles = list(set.intersection(*student_ex_lists)) if student_ex_lists else []
            if common_titles:
                selected_ex_title = st.selectbox("2. Chọn bài tập:", ["-- Chọn bài tập --"] + common_titles)
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
                                num, total = map(int, d.get('score_raw', '0/0').split('/'))
                                d['score_percent'] = (num / total) * 100
                            except: d['score_percent'] = 0
                            student_data_map[d['student_email']].append(d)

                    summary_list, wrong_stats = [], {i: set() for i in range(len(df_exam))}
                    for email in chosen_students:
                        subs = student_data_map[email]
                        if subs:
                            percents = [s['score_percent'] for s in subs]
                            summary_list.append({'Học sinh': email, 'Thấp nhất (%)': min(percents), 'Cao nhất (%)': max(percents)})
                            latest_sub = max(subs, key=lambda x: x['submitted_at'])
                            ans_dict = latest_sub.get('user_answers', {})
                            for i, row in df_exam.iterrows():
                                ck = str(row.get('correct_ans', '')).strip().upper()
                                u_ans = ans_dict.get(str(i))
                                mapping = {clean_nan(row.get('opt_a')):'A', clean_nan(row.get('opt_b')):'B', clean_nan(row.get('opt_c')):'C', clean_nan(row.get('opt_d')):'D'}
                                if mapping.get(u_ans) != ck: wrong_stats[i].add(email)

                    if summary_list:
                        df_summary = pd.DataFrame(summary_list)
                        st.markdown("#### 📊 So sánh sự tiến bộ (%)")
                        c_low, c_high = st.columns(2)
                        with c_low:
                            st.write("**📉 Lần thấp nhất**")
                            st.bar_chart(df_summary.set_index('Học sinh')['Thấp nhất (%)'])
                        with c_high:
                            st.write("**🏆 Lần cao nhất**")
                            st.bar_chart(df_summary.set_index('Học sinh')['Cao nhất (%)'])
                        
                        st.markdown("#### 🎯 Phân tích chi tiết lỗi sai hiện tại")
                        c_list, c_detail = st.columns([1, 1])
                        q_with_errs = [(i, len(emails)) for i, emails in wrong_stats.items() if len(emails) > 0]
                        q_with_errs.sort(key=lambda x: x[1], reverse=True)
                        with c_list:
                            if not q_with_errs: st.success("Cả nhóm đều đúng 100%!")
                            else:
                                sel_q_txt = st.radio("Chọn câu:", [f"Câu {i+1} ({cnt} bạn sai)" for i, cnt in q_with_errs], label_visibility="collapsed")
                                sel_idx = int(sel_q_txt.split(" ")[1]) - 1
                        with c_detail:
                            if q_with_errs:
                                row = df_exam.iloc[sel_idx]
                                with st.container(border=True):
                                    if clean_nan(row.get('audio')) != " ": display_drive_audio(row.get('audio'))
                                    ctx = clean_nan(row.get('context'))
                                    for p in ctx.split(";;"):
                                        if p.strip().startswith("http"): display_drive_image(p.strip())
                                        else: st.markdown(f"*{p.strip()}*")
                                    st.markdown(f"**Câu {sel_idx+1}: {clean_nan(row.get('question'))}**")
                                    ck = str(row.get('correct_ans')).strip().upper()
                                    st.success(f"✅ Đáp án: {ck}. {clean_nan(row.get(f'opt_{ck.lower()}'))}")
                                    st.error(f"❌ Các bạn đang sai: {', '.join(wrong_stats[sel_idx])}")
                    else: st.info("Chưa có dữ liệu.")

def student_page():
    st.sidebar.button("Đăng xuất", on_click=logout)
    full_name = st.session_state.user.get('full_name', 'Học viên')
    st.markdown(f"### 👋 Xin chào, **{full_name}**!")
    st.divider()

    if st.session_state.view_mode == 'list':
        st.subheader("📚 Bài tập của bạn")
        u_email = st.session_state.user['email']
        all_my_subs = [s.to_dict() for s in db.collection('submissions').where('student_email', '==', u_email).stream()]
        exs = db.collection('exercises').where('assigned_to', 'array_contains', u_email).stream()
        for doc in exs:
            ex, ex_id = doc.to_dict(), doc.id
            history = [s for s in all_my_subs if s.get('exercise_title') == ex['title']]
            if history:
                nums = [int(s.get('score_raw','0/0').split('/')[0]) for s in history]
                raws = [s.get('score_raw') for s in history]
                status = f"📉 Thấp: `{raws[nums.index(min(nums))]}` | 🏆 Cao: `{raws[nums.index(max(nums))]}`"
            else: status = "🆕 *Chưa làm*"
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.subheader(f"{ex['type']} - {ex['title']}")
                    st.markdown(f"🔢 Lần làm: `{len(history)}` | {status}")
                with c2: st.button("Vào học ➔", key=f"ex_{doc.id}", on_click=start_lesson_callback, args=(ex, ex_id))

    elif st.session_state.view_mode == 'quiz':
        # (Logic Quiz đã tích hợp display_drive_image có nút Zoom mới)
        st.subheader(f"✍️ {st.session_state.current_ex_info['title']}")
        if st.button("⬅ Thoát"): st.session_state.view_mode = 'list'; st.rerun()
        with st.form("quiz_form"):
            df, last_audio = st.session_state.current_df, None
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
                        st.session_state.user_answers[i] = st.radio(f"q{i}", opts, key=f"q{i}", index=None, label_visibility="collapsed"); st.divider()
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
                                st.session_state.user_answers[i] = st.radio(f"q{i}", opts, key=f"q{i}", index=None, label_visibility="collapsed"); st.write("---")
            if st.form_submit_button("Nộp bài 🏁", use_container_width=True):
                correct = sum(1 for i, r in df.iterrows() if {clean_nan(r.get('opt_a')):'A', clean_nan(r.get('opt_b')):'B', clean_nan(r.get('opt_c')):'C', clean_nan(r.get('opt_d')):'D'}.get(st.session_state.user_answers.get(i)) == str(r.get('correct_ans','')).strip().upper())
                st.session_state.res = f"{correct}/{len(df)}"
                db.collection('submissions').add({'student_email':st.session_state.user['email'], 'exercise_title':st.session_state.current_ex_info['title'], 'score_raw':st.session_state.res, 'user_answers': {str(k): v for k, v in st.session_state.user_answers.items()}, 'submitted_at':datetime.now()})
                st.session_state.view_mode = 'res'; st.rerun()

    elif st.session_state.view_mode == 'res':
        st.balloons(); st.title(f"🎉 Kết quả: {st.session_state.res}")
        u_email = st.session_state.user['email']
        ex_id = st.session_state.current_ex_id
        ex_doc = db.collection('exercises').document(ex_id).get().to_dict()
        can_review = ex_doc.get('review_permissions', {}).get(u_email, False)
        if can_review:
            if st.button("XEM LẠI ĐÁP ÁN (REVIEW)"): st.session_state.view_mode = 'review'; st.rerun()
        else:
            st.info("💡 Giáo viên chưa mở quyền xem lại đáp án cho bài tập này.")
        if st.button("QUAY LẠI TRANG CHỦ"): st.session_state.view_mode = 'list'; st.rerun()

    elif st.session_state.view_mode == 'review':
        st.title("🧐 Review"); df = st.session_state.current_df
        for i, r in df.iterrows():
            st.write(f"**Câu {i+1}: {r.get('question')}**")
            u_ans = st.session_state.user_answers.get(i)
            ck = str(r.get('correct_ans')).strip().upper()
            ct = clean_nan(r.get(f'opt_{ck.lower()}'))
            if {clean_nan(r.get('opt_a')):'A', clean_nan(r.get('opt_b')):'B', clean_nan(get('opt_c')):'C', clean_nan(r.get('opt_d')):'D'}.get(u_ans) == ck:
                st.markdown(f"✅ Đúng: **{u_ans}**")
            else: st.markdown(f"❌ Chọn: {u_ans} | 👉 Đúng: <span class='correct-ans'>{ct}</span>", unsafe_allow_html=True)
            st.divider()
        if st.button("XONG"): st.session_state.view_mode = 'list'; st.rerun()

# --- 6. ĐIỀU HƯỚNG ---
if st.session_state.user is None: login_page()
else: teacher_page() if st.session_state.user.get('role') == 'teacher' else student_page()
