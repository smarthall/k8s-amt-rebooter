FROM python:3.11

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY amt_rebooter.py ./

CMD [ "kopf", "run", "./amt_rebooter.py", "-A" ]
