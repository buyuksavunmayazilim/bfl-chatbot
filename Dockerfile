FROM python:3.11-slim

WORKDIR /app

# Model önbelleği burada dursun (volume'a bağlanacak -> imaj şişmez, her açılışta indirmez)
ENV HF_HOME=/models \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .

# 1) ÖNCE CPU-only torch (CUDA'lı ~2GB yerine ~200MB)
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
# 2) Sonra geri kalanı
RUN pip install -r requirements.txt

COPY . .

# production: --reload YOK
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]