FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY solution.py orchestration.py energytool_rag.py submission_model.py ./
COPY backend ./backend
COPY application_agent ./application_agent
COPY frontend ./frontend
RUN mkdir -p /data
EXPOSE 8000
CMD ["python", "solution.py", "--serve", "--host", "0.0.0.0", "--port", "8000"]
