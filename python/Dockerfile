FROM python
COPY requirements.txt /root/.config/app/
RUN pip install -r /root/.config/app/requirements.txt
ENTRYPOINT ["uwsgi", "--master", "--emperor", "/app/uwsgi.ini", "--die-on-term", "--enable-threads"]