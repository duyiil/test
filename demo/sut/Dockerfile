FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn
COPY demo/sut /app/demo/sut
ENV PYTHONPATH=/app
EXPOSE 8001
CMD ["python", "-m", "uvicorn", "demo.sut.main:app", "--host", "0.0.0.0", "--port", "8001"]
