FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py tdms_utils.py analysis.py report.py generate_test_tdms.py bench_big.py cli.py ./
COPY .streamlit/ .streamlit/
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.headless", "true"]
