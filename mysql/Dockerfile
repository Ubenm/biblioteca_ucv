FROM mysql:8.0
ENV MYSQL_ROOT_PASSWORD=rootpass
ENV MYSQL_DATABASE=docmanager
ENV MYSQL_USER=user
ENV MYSQL_PASSWORD=password
# Asegura que MySQL escuche en todas las interfaces
RUN echo "[mysqld]\nbind-address=0.0.0.0" > /etc/mysql/conf.d/bind.cnf
EXPOSE 3306
