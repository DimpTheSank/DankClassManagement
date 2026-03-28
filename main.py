import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import re
import requests
import time
from datetime import datetime

# --- 1. CẤU HÌNH GIAO DIỆN & CSS ---
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
    .correct-box { border: 2px solid #28a745; background-color: #e8f5e9; padding: 10px; border-radius: 10px; margin-bottom: 5px; }
    .wrong-box { border: 2px solid #dc3545; background-color: #ffebee; padding: 10px; border-radius: 10px; margin-bottom: 5px; }
    .normal-box { border: 1px solid #ddd; padding: 10px; border-radius: 10px; margin-bottom: 5px; color: #666; }
    
    audio { width: 100%; margin-bottom: 20px; border-radius: 10px; background-color: #f1f3f4; }

    @media (max-width: 768px) {
        .context-display { font-size: 19px !important; }
        .stMarkdown p { font-size: 19px !important; }
        div.stButton > button { height: 60px; font-size: 18px !important; margin-bottom: 10px; }
    }

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
    else: cred = credentials.Certificate('data/serviceAccountKey.json')
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- 4. QUẢN LÝ SESSION ---
if 'user' not in st.session_state: st.session_state.user = None
if 'view_mode' not in st.session_state: st.session_state.view_mode = 'list'
if 'current_df' not in st.session_state: st.session_state.current_df = None
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}

def logout():
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.rerun()

def start_lesson_callback(ex, ex_id):
    try:
        df = pd.read_excel(get_drive_url(ex['excel_link']))
        df.columns = [str(c).strip().lower() for c in df.columns]
        st.session_state.current_df, st.session_state.current_ex_info = df, ex
        st.session_state.current_ex_id, st.session_state.view_mode = ex_id, 'quiz'
        st.session_state.user_answers = {}
    except: st.error("Lỗi nạp bài.")

def start_review_direct_callback(ex, history):
    try:
        df = pd.read_excel(get_drive_url(ex['excel_link']))
        df.columns = [str(c).strip().lower() for c in df.columns]
        st.session_state.current_df = df
        latest_sub = max(history, key=lambda x: x['submitted_at'])
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
                u_data = user_ref.to_dict()
                if str(u_data.get('password')) == password:
                    st.session_state.user = {**u_data, 'email': email}
                    st.rerun()
                else: st.error("Sai mật khẩu.")
            else: st.error("Email không tồn tại.")

def teacher_page():
    st.sidebar.button("Đăng xuất", on_click=logout)
    st.title("👨‍🏫 Quản lý Học viên")
    t1, t2, t3 = st.tabs(["📤 Giao bài", "👥 Quản lý", "📊 Thống kê"])
    with t1:
        with st.expander("Giao bài tập mới", expanded=True):
            students = [s.id for s in db.collection('users').where('role', '==', 'student').stream()]
            title, link = st.text_input("Tiêu đề"), st.text_input("Link Excel")
            ex_type = st.selectbox("Loại", ["Reading (Part 5,6,7)", "Listening", "Vocab Game"])
            assigned = st.multiselect("Giao cho:", students)
            if st.button("🚀 Đăng bài", use_container_width=True):
                db.collection('exercises').add({'title': title, 'type': ex_type, 'excel_link': link, 'assigned_to': assigned, 'created_at': firestore.SERVER_TIMESTAMP, 'review_permissions': {e: False for e in assigned}})
                st.success("Đã đăng bài!")
    with t2:
        all_st = [s.id for s in db.collection('users').where('role', '==', 'student').stream()]
        sel_st = st.selectbox("Chọn học sinh:", ["-- Chọn --"] + all_st)
        if sel_st != "-- Chọn --":
            exs = db.collection('exercises').where('assigned_to', 'array_contains', sel_st).stream()
            for doc in exs:
                ex, ex_id = doc.to_dict(), doc.id
                with st.expander(f"📝 {ex['title']}"):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"Loại: {ex['type']}")
                    perms = ex.get('review_permissions', {})
                    if c2.toggle("Cho phép Review", value=perms.get(sel_st, False), key=f"rev_{ex_id}_{sel_st}"):
                        perms[sel_st] = True
                        db.collection('exercises').document(ex_id).update({'review_permissions': perms})
                    else:
                        perms[sel_st] = False
                        db.collection('exercises').document(ex_id).update({'review_permissions': perms})
                    if c3.button("🗑️ Xoá bài", key=f"del_{ex_id}_{sel_st}"):
                        new_a = [e for e in ex['assigned_to'] if e != sel_st]
                        if not new_a: db.collection('exercises').document(ex_id).delete()
                        else: db.collection('exercises').document(ex_id).update({'assigned_to': new_a})
                        st.rerun()
    with t3:
        chosen = st.multiselect("Chọn nhóm học sinh:", all_st)
        if chosen:
            student_ex_lists = []
            for email in chosen:
                exs = db.collection('exercises').where('assigned_to', 'array_contains', email).stream()
                student_ex_lists.append({doc.to_dict()['title'] for doc in exs})
            common = list(set.intersection(*student_ex_lists)) if student_ex_lists else []
            if common:
                sel_title = st.selectbox("Chọn bài tập:", ["-- Chọn --"] + common)
                if sel_title != "-- Chọn --":
                    ex_doc = db.collection('exercises').where('title', '==', sel_title).limit(1).get()[0]
                    df_ex = pd.read_excel(get_drive_url(ex_doc.to_dict()['excel_link']))
                    df_ex.columns = [str(c).strip().lower() for c in df_ex.columns]
                    all_s = db.collection('submissions').where('exercise_title', '==', sel_title).stream()
                    data_map = {e: [] for e in chosen}
                    for s in all_s:
                        d = s.to_dict()
                        if d['student_email'] in chosen:
                            try:
                                n, t = map(int, d.get('score_raw', '0/0').split('/'))
                                d['score_percent'] = (n / t) * 100
                            except: d['score_percent'] = 0
                            data_map[d['student_email']].append(d)
                    summary, wrong_stats = [], {i: set() for i in range(len(df_ex))}
                    for e in chosen:
                        subs = data_map[e]
                        if subs:
                            per = [s['score_percent'] for s in subs]
                            summary.append({'Học sinh': e, 'Thấp nhất (%)': min(per), 'Cao nhất (%)': max(per)})
                            latest = max(subs, key=lambda x: x['submitted_at'])
                            ans = latest.get('user_answers', {})
                            for i, row in df_ex.iterrows():
                                ck = str(row.get('correct_ans', '')).strip().upper()
                                mapping = {clean_nan(row.get('opt_a')):'A', clean_nan(row.get('opt_b')):'B', clean_nan(row.get('opt_c')):'C', clean_nan(row.get('opt_d')):'D'}
                                if mapping.get(ans.get(str(i))) != ck: wrong_stats[i].add(e)
                    if summary:
                        df_s = pd.DataFrame(summary)
                        st.markdown("#### 📊 Tiến độ (%)")
                        c_l, c_h = st.columns(2)
                        c_l.write("**📉 Thấp nhất**"); c_l.bar_chart(df_s.set_index('Học sinh')['Thấp nhất (%)'])
                        c_h.write("**🏆 Cao nhất**"); c_h.bar_chart(df_s.set_index('Học sinh')['Cao nhất (%)'])
                        st.markdown("#### 🎯 Câu sai nhiều nhất")
                        cl, cr = st.columns([1, 1])
                        q_errs = sorted([(i, len(ems)) for i, ems in wrong_stats.items() if ems], key=lambda x: x[1], reverse=True)
                        with cl:
                            sq = st.radio("Câu:", [f"Câu {i+1} ({c} bạn sai)" for i, c in q_errs], label_visibility="collapsed")
                            idx = int(sq.split(" ")[1]) - 1
                        with cr:
                            r = df_ex.iloc[idx]
                            with st.container(border=True):
                                if clean_nan(r.get('audio')) != " ": display_drive_audio(r.get('audio'))
                                ctx = clean_nan(r.get('context'))
                                for p in ctx.split(";;"):
                                    if p.strip().startswith("http"): display_drive_image(p.strip())
                                    else: st.markdown(f"*{p.strip()}*")
                                st.markdown(f"**Câu {idx+1}: {clean_nan(r.get('question'))}**")
                                ck = str(r.get('correct_ans')).strip().upper()
                                st.success(f"✅ Đáp án: {ck}. {clean_nan(r.get(f'opt_{ck.lower()}'))}")
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
            can_rev = ex.get('review_permissions', {}).get(u_email, False)
            with st.container(border=True):
                c1, c2 = st.columns([4, 1.5])
                with c1:
                    st.subheader(f"{ex['type']} - {ex['title']}")
                    if history:
                        scs = [int(s.get('score_raw','0/0').split('/')[0]) for s in history]
                        st.markdown(f"🔢 Lần làm: `{len(history)}` | 📉 Thấp: `{min(scs)}` | 🏆 Cao: `{max(scs)}` / {history[0].get('score_raw','').split('/')[-1]}")
                    else: st.markdown("🆕 *Chưa làm*")
                with c2:
                    st.button("Làm bài ➔", key=f"btn_{ex_id}", on_click=start_lesson_callback, args=(ex, ex_id), use_container_width=True)
                    if history and can_rev:
                        st.button("Xem lại 🧐", key=f"rev_{ex_id}", on_click=start_review_direct_callback, args=(ex, history), use_container_width=True)

    elif st.session_state.view_mode == 'quiz':
        st.subheader(f"✍️ {st.session_state.current_ex_info['title']}")
        if st.button("⬅ Thoát"): st.session_state.view_mode = 'list'; st.rerun()
        with st.form("quiz_form"):
            df, answers = st.session_state.current_df, {}
            df['ctx_tmp'] = df['context'].fillna('').astype(str).str.strip()
            df['aud_tmp'] = df['audio'].fillna('').astype(str).str.strip()
            df['group'] = ((df['ctx_tmp'] != df['ctx_tmp'].shift()) | (df['aud_tmp'] != df['aud_tmp'].shift())).cumsum()
            
            # BIẾN GHI NHỚ AUDIO TRONG FORM
            last_audio_rendered = None
            
            for _, group_df in df.groupby('group'):
                first = group_df.iloc[0]
                curr_aud = str(first.get('aud_tmp')).strip()
                
                # CHỈ HIỆN AUDIO NẾU NÓ KHÁC VỚI AUDIO ĐÃ HIỆN TRƯỚC ĐÓ
                if curr_aud != "" and curr_aud != last_audio_rendered:
                    display_drive_audio(curr_aud)
                    last_audio_rendered = curr_aud
                
                ctx = clean_nan(first.get('context'))
                if ctx.lower() in [" ", "nan", "none"]:
                    for i, r in group_df.iterrows():
                        st.write(f"**Câu {i+1}: {clean_nan(r.get('question','Listen'))}**")
                        opts = [clean_nan(r.get('opt_a')), clean_nan(r.get('opt_b')), clean_nan(r.get('opt_c'))]
                        if clean_nan(r.get('opt_d')).upper() != "NONE" and clean_nan(r.get('opt_d')) != " ": opts.append(clean_nan(r.get('opt_d')))
                        answers[i] = st.radio(f"q{i}", opts, key=f"q{i}", index=None, label_visibility="collapsed"); st.divider()
                else:
                    st.markdown("---")
                    l, r_col = st.columns([1, 1])
                    with l:
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
        st.title("🧐 Review đáp án chi tiết")
        if st.button("⬅ Quay lại danh sách"): st.session_state.view_mode = 'list'; st.rerun()
        df = st.session_state.current_df
        df['ctx_tmp'] = df['context'].fillna('').astype(str).str.strip()
        df['aud_tmp'] = df['audio'].fillna('').astype(str).str.strip()
        df['group'] = ((df['ctx_tmp'] != df['ctx_tmp'].shift()) | (df['aud_tmp'] != df['aud_tmp'].shift())).cumsum()
        
        last_audio_review = None
        for _, group_df in df.groupby('group'):
            first = group_df.iloc[0]
            ctx = clean_nan(first.get('context'))
            curr_aud = str(first.get('aud_tmp')).strip()
            
            if ctx.lower() not in [" ", "nan", "none"]:
                st.markdown("---")
                l_rev, r_rev = st.columns([1, 1])
                with l_rev:
                    with st.container(height=650):
                        # HIỆN AUDIO NẾU CHƯA XUẤT HIỆN
                        if curr_aud != "" and curr_aud != last_audio_review:
                            display_drive_audio(curr_aud)
                            last_audio_review = curr_aud
                        for p in ctx.split(";;"):
                            if p.strip().startswith("http"): display_drive_image(p.strip())
                            else: st.markdown(f'<div class="context-display">{p.strip()}</div>', unsafe_allow_html=True)
                with r_rev:
                    with st.container(height=650):
                        for i, r in group_df.iterrows():
                            st.write(f"**Câu {i+1}: {clean_nan(r.get('question'))}**")
                            u_ans = st.session_state.user_answers.get(i); ck_letter = str(r.get('correct_ans')).strip().upper()
                            opts = {'A': clean_nan(r.get('opt_a')), 'B': clean_nan(r.get('opt_b')), 'C': clean_nan(r.get('opt_c')), 'D': clean_nan(r.get('opt_d'))}
                            for let, txt in opts.items():
                                if txt == " " or (let == 'D' and txt.upper() == "NONE"): continue
                                is_correct, is_mine = (let == ck_letter), (txt == u_ans)
                                if is_correct and is_mine: st.markdown(f'<div class="correct-box">✅ <b>{let}. {txt}</b> (Bạn chọn đúng)</div>', unsafe_allow_html=True)
                                elif is_correct: st.markdown(f'<div class="correct-box">🟢 <b>{let}. {txt}</b> (Đáp án đúng)</div>', unsafe_allow_html=True)
                                elif is_mine: st.markdown(f'<div class="wrong-box">❌ <b>{let}. {txt}</b> (Bạn chọn sai)</div>', unsafe_allow_html=True)
                                else: st.markdown(f'<div class="normal-box">{let}. {txt}</div>', unsafe_allow_html=True)
                            st.write("---")
            else:
                if curr_aud != "" and curr_aud != last_audio_review:
                    display_drive_audio(curr_aud)
                    last_audio_review = curr_aud
                for i, r in group_df.iterrows():
                    st.write(f"**Câu {i+1}: {clean_nan(r.get('question','Listen'))}**")
                    u_ans = st.session_state.user_answers.get(i); ck_letter = str(r.get('correct_ans')).strip().upper()
                    opts = {'A': clean_nan(r.get('opt_a')), 'B': clean_nan(r.get('opt_b')), 'C': clean_nan(r.get('opt_c')), 'D': clean_nan(r.get('opt_d'))}
                    for let, txt in opts.items():
                        if txt == " " or (let == 'D' and txt.upper() == "NONE"): continue
                        if let == ck_letter and txt == u_ans: st.markdown(f'<div class="correct-box">✅ <b>{let}. {txt}</b> (Bạn chọn đúng)</div>', unsafe_allow_html=True)
                        elif let == ck_letter: st.markdown(f'<div class="correct-box">🟢 <b>{let}. {txt}</b> (Đáp án đúng)</div>', unsafe_allow_html=True)
                        elif txt == u_ans: st.markdown(f'<div class="wrong-box">❌ <b>{let}. {txt}</b> (Bạn chọn sai)</div>', unsafe_allow_html=True)
                        else: st.markdown(f'<div class="normal-box">{let}. {txt}</div>', unsafe_allow_html=True)
                    st.divider()

        st.button("XONG", on_click=lambda: st.session_state.update({"view_mode":"list"}), use_container_width=True)

# --- 6. ĐIỀU HƯỚNG ---
if st.session_state.user is None: login_page()
else: teacher_page() if st.session_state.user.get('role') == 'teacher' else student_page()
