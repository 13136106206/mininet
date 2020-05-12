#!/usr/bin/python

import os
import threading

# if 0 == servers:
# ues remote tinc proxy
servers = 8
clients = 16
need_start_sh = True

remote_server_host = "\
Address=58.20.63.23\n\
Port=50069\n\
-----BEGIN PUBLIC KEY-----\n\
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA8hyOHaVNiVsZwOex8/Y1\n\
dkgwYIv8e0xjhdnShda8pQZh7eFyKeGxlP4HBRdtSP/n2XdqV0lnFQP+mjd0cHfC\n\
VHvEJPxtu+J+Gs384AmX2BLTZOV4hK/x1Hc7jL0Z5BS4FYGQIu3BwZMBVXfgGq1K\n\
J3z3ymCBCeez5HM8dR22oVzO4BA7cCyC1WajyaKi0jN+dy8ltoHWOPgnebCEBSqN\n\
+mlEtS7+gGaqB/MJiTb8h9B4FvPk0sgGTRxWle8NOkEmDR2KrUpjtjgy7P3ctsHH\n\
LX4Agzj1hrpuZHVc7ejV8n/0phY4VwvHWmsAoHTHFGdlvfj2UcUuVZkfs47MfSkb\n\
XQIDAQAB\n\
-----END PUBLIC KEY-----\n\
"


def creat_conf():
    copy_server_pubkey()

    thread_pool = []

    for i in range(1, servers + clients + 1):
        s = str(i)
        try:
            os.mkdir("/etc/tinc/" + s)
        except:
            pass
        try:
            os.mkdir("/etc/tinc/" + s + "/hosts")
        except:
            pass
        for j in range(0, 5):
            msg = ""
            if j == 0:
		if i <= servers:
                	f = open("/etc/tinc/" + s + "/hosts/vpnserver_" + s, "w+")
		else :
                	f = open("/etc/tinc/" + s + "/hosts/c_" + str((int(s)-7)/2) + "_" + str((int(s)-7)%2 + 1) , "w+")
                msg = "Address=10.0.0." + s + "\n" + \
                    "PrivateKeyFile = /etc/tinc/" + s + "/rsa_key.priv \n" + \
                    "PublicKeyFile = /etc/tinc/" + s + "/rsa_key.pub"
            elif j == 1:
                f = open("/etc/tinc/" + s + "/nets.boot", "w+")
                msg = "## This file contains all names of the networks to be started on system startup.\ntest"

            elif j == 2:
                f = open("/etc/tinc/" + s + "/tinc.conf", "w+")
                if i <= servers:
 		    msg = "Name = vpnserver_" + s
                    msg += "\nDevice = /dev/net/tun\nMode = switch"
                    for k in range(1, servers + 1):
                        msg += "\nConnectTo = vpnserver_" + str(k)

                    	if 0 == servers:
                        	msg += "\nConnectTo = vpnserver"

                else:
		    msg = "Name = c_" + str((int(s)-7)/2) + "_" + str((int(s)-7)%2 + 1) + "\nDevice = /dev/net/tun\nMode = switch"
                    #for k in range(1, servers + 1):
                    msg += "\nConnectTo = vpnserver"
		msg += "\nPort = " + str(i + 12300)

            elif j == 3:
                f = open("/etc/tinc/" + s + "/tinc-down", "w+")
                msg = "ifconfig $INTERFACE down"
            elif j == 4:
                f = open("/etc/tinc/" + s + "/tinc-up", "w+")
                msg = "ifconfig $INTERFACE 10.1.0." + s + " netmask 255.255.0.0\n" + \
                    "route add -host 10.255.255.254 dev $INTERFACE\n" + \
                    "echo 1 > /proc/sys/net/ipv4/ip_forward\n" + \
                    "iptables -t nat -F\n" + \
                    "iptables -t nat -A POSTROUTING -s 10.1.0.0/24 -o h" + s + "-eth0 -j MASQUERADE"
            f.write(msg)
            f.close()

	f = open("/etc/tinc/" + s + "/s", "w+")
        msg = "tinc -c . --pidfile=tinc.pid $*\n"
	f.write(msg)
        f.close()

        os.chmod("/etc/tinc/" + s + "/s", 777)
        os.chmod("/etc/tinc/" + s + "/tinc-up", 777)
        os.chmod("/etc/tinc/" + s + "/tinc-down", 777)
        handle = threading.Thread(target=create_host_pubkey, args=(s, ))
        handle.start()
        thread_pool.append(handle)

    for i in range(1, servers + clients + 1):
        s = str(i)
        if need_start_sh:
            f = open("/etc/tinc/" + s + "/start", "w+")
	    if i <= servers:
                msg = "#!/bin/bash\n" + "tincd -c /etc/tinc/" + s + " --pidfile /etc/tinc/" + s + "/tinc.pid -D -d 1"
	    else :
                msg = "#!/bin/bash\n" + "sudo /etc/tinc/" + s  + "/tincd -c /etc/tinc/" + s + " --pidfile /etc/tinc/" + s + "/tinc.pid -D -d 1"	
                os.system("cp /usr/local/sbin/tincd_old /etc/tinc/" + s + "/tincd")
            f.write(msg)
            f.close()
            os.system("chmod 0755 /etc/tinc/" + s + "/start")

        s = str(i)
        os.system("rm -rf /etc/tinc/" + s + "/hosts")

    while True:
        if len(thread_pool) == 0:
            break
        i = 0
        for handle in thread_pool:
            if not handle.isAlive():
                thread_pool.pop(i)
            i += 1

    for i in range(1, servers + clients + 1):
        s = str(i)
	if i > servers :
	    os.system("mkdir /etc/tinc/" + s + "/hosts")
            os.system("cp /etc/tinc/hosts/c_" + str((i-7)/2) + "_" + str((i-7)%2 + 1) + " /etc/tinc/" + s + "/hosts")
            os.system("cp /etc/tinc/hosts/vpnserver_" + str((i-7)/2) + " /etc/tinc/" + s + "/hosts/vpnserver")
	else :
            os.system("cp -rf /etc/tinc/hosts /etc/tinc/" + s + "/hosts")


def clean_conf_dir():
    os.system("rm -rf /etc/tinc/")
    os.system("rm -rf /etc/tinc/hosts")
    os.system("mkdir /etc/tinc/hosts -p")


def copy_server_pubkey():
    if 0 == servers:
        f = open("/etc/tinc/hosts/vpnserver", "w+")
        f.write(remote_server_host)
        f.close()


def create_host_pubkey(s):
    os.system("openssl genrsa -out /etc/tinc/" + s + "/rsa_key.priv -f4 2048")
    os.system("openssl rsa -in /etc/tinc/" + s + "/rsa_key.priv -pubout -out /etc/tinc/" + s + "/rsa_key.pub")

    # get pub_key
    f = open("/etc/tinc/" + s + "/rsa_key.pub", "r")
    pubkey = f.read()
    f.close()

    if int(s) <= servers:
        pubkey = "Address=10.0.0." + s + "\nPort =" + str(int(s) + 12300) + "\n" + pubkey
    if int(s) <= servers :
    	f = open("/etc/tinc/hosts/vpnserver_" + s, "w+")
    else :
    	f = open("/etc/tinc/hosts/c_" + str((int(s)-7)/2) + "_" + str((int(s)-7)%2 + 1) , "w+")
    f.write(pubkey)
    f.close()


if __name__ == '__main__':
    clean_conf_dir()
    creat_conf()
