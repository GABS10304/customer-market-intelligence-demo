FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV STREAMLIT_GATHER_USAGE_STATS=false
EXPOSE 8501
CMD ["streamlit", "run", "PM Evidence AI Portal/Home.py", "--server.address=0.0.0.0"]