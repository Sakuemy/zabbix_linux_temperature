Должен быть установлен python3
	sudo apt install python3

sudo mkdir -p /opt/hardware-monitoring
sudo nano /opt/hardware-monitoring/hwmon_read.py
sudo chown root:root /opt/hardware-monitoring/hwmon_read.py
sudo chmod 755 /opt/hardware-monitoring/hwmon_read.py

Узнаем пользователя агента:
	ps -o user,group,comm -C zabbix_agentd

Создадим отдельное правило sudo (чтобы можно было только запускать от root):
	sudo visudo -f /etc/sudoers.d/zabbix-hardware
		zabbix ALL=(root) NOPASSWD: /usr/bin/python3 /opt/hardware-monitoring/hwmon_read.py
	Проверим синтаксис:
		sudo visudo -c

Добавляем новый конфиг в zabbix agent:
	sudo nano /etc/zabbix/zabbix_agentd.d/hardware.conf
		UserParameter=hwmon.read.json,sudo /usr/bin/python3 /opt/hardware-monitoring/hwmon_read.py

Нужно проверить что в конфиге zabbix agent (/etc/zabbix/zabbix_agentd.conf) есть параметр:
	Include=/etc/zabbix/zabbix_agentd.d/*.conf

Перезапускаем агент:
	sudo systemctl restart zabbix-agent

Проверяем работу:
	sudo systemctl status zabbix-agent --no-pager
	zabbix_agentd -t hwmon.read.json

Далее в серверной части импортируем hwmon_template.yaml в шаблоны (делаем 1 раз)

Добавляем шаблон на серверах на которых настроен этот скрипт и через пару минут данные появятся