st.markdown("---")
l, r_col = st.columns([1, 1])
with l:
                    with st.container(height=650):
                    with st.container(height=900):
for p in ctx.split(";;"):
if p.strip().startswith("http"): display_drive_image(p.strip())
else: st.markdown(f'<div class="context-display">{p.strip()}</div>', unsafe_allow_html=True)
with r_col:
                    with st.container(height=650):
                    with st.container(height=900):
for i, r in group_df.iterrows():
st.write(f"**Câu {i+1}: {clean_nan(r.get('question'))}**")
opts = [clean_nan(r.get(f'opt_{let}')) for let in ['a','b','c','d'] if clean_nan(r.get(f'opt_{let}')) != " " and clean_nan(r.get(f'opt_{let}')).upper() != "NONE"]
@@ -395,14 +395,14 @@ def student_page():
st.markdown("---")
l_rev, r_rev = st.columns([1, 1])
with l_rev:
                    with st.container(height=650):
                    with st.container(height=900):
if curr_aud != "" and curr_aud != last_audio_review:
display_drive_audio(curr_aud); last_audio_review = curr_aud
for p in ctx.split(";;"):
if p.strip().startswith("http"): display_drive_image(p.strip())
else: st.markdown(f'<div class="context-display">{p.strip()}</div>', unsafe_allow_html=True)
with r_rev:
                    with st.container(height=650):
                    with st.container(height=900):
for i, r in group_df.iterrows():
st.write(f"**Câu {i+1}: {clean_nan(r.get('question'))}**")
u_ans = st.session_state.user_answers.get(i)
