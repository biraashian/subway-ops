FROM python:3.12-slim

WORKDIR /app

# Install deps first so layer caching does its job across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then the source tree.
COPY . .

EXPOSE 8501

# streamlit_app.py at the repo root registers our pages via
# st.navigation() — that's the canonical entry for both Streamlit Cloud
# and Fly.io.
CMD ["streamlit", "run", "streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
