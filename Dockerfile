FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY web ./web
ENV PYTHONPATH=/app/src LLM_BACKEND=mock
EXPOSE 8000
CMD ["uvicorn", "iparty.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
