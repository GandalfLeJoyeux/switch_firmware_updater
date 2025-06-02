import paramiko
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime
import csv
import os
import re

# Configuration des identifiants (à remplacer par des variables d'environnement en production)
username = os.getenv("username")
password = os.getenv("password")


# Identifiants pour une utilisation manuel
#username = ""
#password = ""

# Fichier source contenant la liste des IP des switches
ip_source = "sw_conf.txt"

hosts = []
with open(ip_source, "r") as ip_swt:
    for line in ip_swt.readlines():
        hosts.append({"ip": line.strip()})

# Nombre de thread max
max_threads = 50


def hote(host):
    """
    Fonction principale pour chaque hôte
    Gère la connexion SSH, SFTP et l'exécution des commandes
    """
    client = None
    shell = None
    try:
        # Initialisation de la session SSH principale
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=host["ip"],
            username=username,
            password=password,
            timeout=240,
            banner_timeout=180,
        )

        time.sleep(3)  # Pause pour assurer la stabilité de la connexion

        # Initialisation de la session SFTP
        sftp_client = paramiko.SSHClient()
        sftp_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        sftp_client.connect(
            hostname=host["ip"],
            username=username,
            password=password,
            timeout=240,
            banner_timeout=180,
        )

        # Création d'un shell interactif
        shell = client.invoke_shell()
        time.sleep(3)
        ##########
        # Heure du redémarrage "HH:MM MM/DD"
        date = "00:00 00/00"
        
        # Adresse du serveur sntp
        sntp = "0.0.0.0"

        initialisation(shell, sntp)

        # Ouverture de la session SFTP
        time.sleep(3)
        sftp = sftp_client.open_sftp()
        time.sleep(3)

        check_update(shell, host)

        # switch_maj(shell, sftp, host, date)

    except TimeoutError as e:
        erreur(host, e)
        print(f"Timeout pour l'hôte {host["ip"]} : {e}")
    except Exception as e:
        erreur(host, e)
        print(f"Erreur avec l'hôte {host["ip"]} : {e}")
    finally:
        # Ferme les connexions
        client.close()
        sftp.close()


def switch_maj(shell, sftp, host, date):
    """
    Gère de A à Z la mise à jour d'un switch.
    date : 'HH:MM MM/DD'

    """
    # Récupération des informations nécéssaire
    get_hostname(shell, host)
    get_current_version(shell, host)
    get_flash(shell, host)
    get_last_version(host)

    firmware_path = f'versions/{host["last_version"]}' # Chemin vers la dernière version disponible
    up_to_date = is_uptodate(host, host["last_version"]) # Vérification de la 'current_version' pour savoir si il est à jour.
    if up_to_date == True:
        with open("rapport.txt", "+a", encoding="utf-8") as file:
            file.write(
                f'{time.ctime()} | {host["hostname"]}({host["ip"]}) est déjà à jour\n'
            )
            # print(f'{host["hostname"]}({host["ip"]}) est déjà à jour')
        return
    print(f'{host["hostname"]}({host["ip"]}) : {up_to_date}')
    backup_running(shell, sftp, host)
    sftp_maj(sftp, firmware_path)
    reload_at(shell, host, date)
    return


def check_update(shell, host, current_flash=True):
    """
    Fonction permettant de savoir si le switch est à jour.
    current_flash = vérifie la current version (True) ou la flash version (False)
    """
    get_hostname(shell, host)
    get_current_version(shell, host)
    get_flash(shell, host)
    get_last_version(host)

    up_to_date = is_uptodate(host, host["last_version"], current_flash)
    if up_to_date == True:
        with open("rapport.txt", "+a", encoding="utf-8") as file:
            file.write(
                f'{time.ctime()} | {host["hostname"]}({host["ip"]}) est déjà à jour\n'
            )
            # print(f'{host["hostname"]}({host["ip"]}) est déjà à jour')
        return
    print(f'{host["hostname"]}({host["ip"]}) : {up_to_date}')


def initialisation(shell, sntp):
    """
    Configure le terminal, active le transfert SFTP et met à jour la date&heure du switch
    """
    wait(shell)
    shell.send(
        "A\n"  # Appuyer sur une touche pour commencer
        "no page\n"  # Désactive la pagination
        "terminal width 1920\n"  # Définit une largeur de terminal large
        "\nconf\n"  # Entre en mode configuration
        "no tftp client\n"  # Désactive TFTP
        "no tftp server\n"
        "ip ssh filetransfer\n"  # Active le transfert de fichiers SSH
        "exit\n"  # Sort du mode configuration
    )
    set_time(shell, sntp)
    wait(shell)
    wr_mem(shell)
    return


def set_time(shell, sntp):
    """
    Met à jour la configuration sntp et renseigne la bonne date.
    """
    date = datetime.now().strftime("%m/%d/%Y %H:%M")
    shell.send(
        "\nconf\n"
        "time daylight-time-rule middle-europe-and-portugal\n"
        "time timezone 60\n"
        f"sntp server {sntp}\n"
        f"sntp server priority 1 {sntp}\n"
        "sntp unicast\n"
        "timesync sntp\n"
        f"time {date}"
        "exit\n"
    )
    wait(shell)
    wr_mem(shell)

def erreur(host, e):
    """
    Enregistre les erreurs dans un fichier de log
    """
    with open("erreur.txt", "+a") as file:
        file.write(f"{time.ctime()} | {host} : {e}\n")


def wait(shell, timeout=20):
    """
    Fonction qui attend la réponse du switch, après chaque commande qui renvoie quelque chose (show running-config par exemple).
    Permet aussi de s'assurer qu'une commande à bien été appliqué avant de passer à la prochaine.
    """
    start_time = time.time()
    while not shell.recv_ready():
        if time.time() - start_time > timeout:
            raise TimeoutError("Aucune donnée reçue dans le délai imparti.")
    time.sleep(0.5)


# Write memory, sauvegarde la configuration en cours.
def wr_mem(shell):
    shell.send("\nwrite memory\n")
    wait(shell)
    time.sleep(2)
    return



# Renvoie la date et l'heure du switch
def show_time(shell, host):
    tampon = ""
    shell.send("show time\n")
    wait(shell)
    tampon += shell.recv(65535).decode()
    date = re.search(
        r"[A-Za-z]{3} [A-Za-z]{3} \d{1,2} \d{1,2}:\d{2}:\d{2} \d{4}", tampon
    )
    return f"{host["ip"]} : {date.group()}"


def get_last_version(host):
    """
    Va chercher dans le dossiers ./versions/ le firmware qui correspond au modèle du switch.
    Il compare les premières lettres de la version du switch avec les premières lettres des versions disponible.
    YA.16.11.0024 [flash_version]-> YA_16_11_0025.swi [last_version]
    """
    model = host["flash_version"]
    versions = os.listdir("versions/")
    for f in versions:
        if model.split(".")[0] == f.split("_")[0]:
            path = f
            host["last_version"] = path
            return path


def is_uptodate(host, last_version, current_flash=True) -> bool:
    """
    Booléen, indiquant, si une version de firmware différente de celle du switch est disponible.
    True = Pas de nouvelle version disponible -> à jour
    False = Une version différente est disponible -> pas à jour
    Par défaut elle vérifie la version qui tourne sur le switch (current_version) mais peut utiliser la version chargé (flash_version),
    il faut passer l'argument current_flash à False.
    Utile pour vérifier que le switch à bien redémarré après une mise à jour.
    """
    if current_flash:
        firmware = host["current_version"].replace(".", "_") + ".swi"
    else:
        firmware = host["flash_version"].replace(".", "_") + ".swi"
    if firmware == last_version:
        return True
    return False


def reload(shell):
    """
    Fonction pour envoyer la commande reload (Reload instantané, prévilégié "reload_at")
    Ne surtout pas l'utiliser juste après avoir téléversé un firmware avec sftp (risque de casse)
    """
    tampon = ""  # Stocker la sortie reçue
    while True:
        wait(shell)  # Attendre que le shell soit prêt
        tampon += shell.recv(65535).decode()  # Lire la sortie du shell
        if (
            "Rebooting the System" in tampon
        ):  # Vérifier si le message est présent "Warning!", "Rebooting the System"
            print(f"Le switch {host['ip']} est en train de redémarrer.")
            break  # Sortir de la boucle
        # Envoyer les commandes nécessaires
        wr_mem(shell)  # Sauvegarde la conf avant
        wait(shell)
        shell.send(f"\nreload\n")  # Envoyer la commande reload
        wait(shell)
        shell.send("y\n")  # Confirmer le reboot
        wait(shell)
    return  # tampon #print("Commande 'reload' envoyée avec succès.")


def show_reload_at(shell, host):
    """
    Renvoie pour les switches compatible avec la commande 'show reload at',
    la date et l'heure à laquelle un 'reload' est programmé.
    """
    tampon = ""
    shell.send("show reload at\n")
    wait(shell)
    tampon += shell.recv(65535).decode("utf-8", errors="ignore")
    try:
        for l in tampon.splitlines():
            if "Reload scheduled" in l:
                reload = (re.search(r"    (.+)", l)).group(1).strip()
                return f"{host["ip"]} : {reload}"
    except:
        return f"{host["ip"]} no reload scheduled"


def reload_at(shell, host, date: str):
    """
    Programme un redémarrage de manière douce du switch 
    date="HH:MM MM/DD"
    """
    tampon = ""  # Stocker la sortie reçue
    while "Reload scheduled" not in tampon:
        # wait(shell)  # Attendre que le shell soit prêt
        # Envoyer les commandes nécessaires
        wr_mem(shell)  # Sauvegarde la conf avant
        wait(shell)
        shell.send(f"\nreload at {date}\n")  # Envoyer la commande reload
        wait(shell)
        shell.send("y\n")  # Confirmer le reboot
        wait(shell)
        shell.send("show reload at")
        wait(shell)
        time.sleep(1)
        tampon += shell.recv(65535).decode()
    # print("Commande 'reload' envoyée avec succès.")
    return f"{host["ip"]} redemarrera à {date}"



def get_running_config(shell):
    """
    Renvoie la configuration actuelle du switch.
    """
    tampon = ""
    try:
        # Envoyer la commande 'show running-config'
        shell.send("show running-config\n")
        wait(shell)
        time.sleep(5)
        # Lire la sortie en boucle
        while shell.recv_ready():
            tampon += shell.recv(65535).decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Erreur lors de l'exécution de 'show running-config': {e}")

    return tampon


def get_hostname(shell, host):
    """
    Récupère le hostname du switch dans le "running config".
    """
    tampon = get_running_config(shell)
    for l in tampon.splitlines():
        if "hostname" in l:
            match = re.search(r'hostname\s+"([^"]+)"', l)
            if match:
                hostname = match.group(1)
                host["hostname"] = hostname
                return host
            else:
                raise Exception("aucun hostname trouvé")
            

def get_current_version(shell, host):
    """
    Renvoie la version du firmware actuellement utilisé sur le switch. 
    """
    tampon = get_running_config(shell)
    for l in tampon.splitlines():
        if "Created on release" in l:
            version = (re.search(r"Created on release (.+)", l)).group(1).strip("#")
    host["current_version"] = version
    return f"{host["ip"]} : {version}"


def get_flash(shell, host):
    """
    Renvoie la version du firmware chargé dans la mémoire du switch.
    Seulement la partition primaire.
    """
    tampon = ""
    shell.send("show flash\n")
    wait(shell)
    time.sleep(5)
    tampon += shell.recv(65535).decode()
    for l in tampon.splitlines():
        match = re.search(r"Primary.*\d{2}/\d{2}/\d{2} (.+)", l) # Expression régulière permettant de matcher la version de la partition primaire.
        if match:
            host["flash_version"] = match.group(1).strip()
            return f"{host["ip"]} : {host["flash_version"]}"
    return f"{host["ip"]} : queutchi nada voilou ???"


def backup_running(shell, sftp, host):
    """
    Sauvegarde la configuration du switch dans un fichier
    Format: YYYYMMDD/YYYYMMDD_HOSTNAME_IP.cfg

    Args:
        shell: Session shell SSH active
        sftp: Session SFTP active
        host (dict): Dictionnaire contenant les informations du switch
    """
    # Récupération du hostname du switch
    get_hostname(shell, host)

    # Création du nom de fichier avec la date, le hostname et l'IP
    file_name = (
        f"{datetime.now().strftime("%Y%m%d")}_{host["hostname"]}_{host["ip"]}.cfg"
    )
    time.sleep(3)
    try:
        # Création du dossier de sauvegarde avec la date
        backup_dir = f"config/{datetime.now().strftime("%Y%m%d")}"
        os.makedirs(backup_dir, exist_ok=True)

        # Récupération et sauvegarde du fichier de configuration
        sftp.get("/cfg/running-config", f"{backup_dir}/{file_name}")
        return
    except Exception as e:
        print(f"SFTP failed for {host["ip"]} : {e}")


def sftp_maj(sftp, path, partition=True):
    """
    Copie le firmware spécifié dans le chemin de la variable path,
    en le renommant primary(True)/secondary(False)
    en fonction de la partition que l'on veux modifier.
    Par défaut primary(True).
    """
    if partition:
        ps = "primary"
    else:
        ps = "secondary"
    try:
        sftp.put(f"{path}", f"/os/{ps}", confirm=False)
    except Exception as e:
        print(e)



# Envoie les commandes nécessaire pour téléverser le firmware, fonctionne uniquement avec les mêmes modèles.
# Ne plus l'utiliser svp
def tftp_maj(shell, host, ip_tftp, chemin_version):
    tampon = ""  # Stocker la sortie reçue
    while "Validating and Writing System Software to FLASH..." not in tampon:
        wait(shell)  # Attendre que le shell soit prêt
        # Envoyer les commandes nécessaires
        wait(shell)
        wr_mem(shell)  # Sauvegarde la conf avant
        wait(shell)
        shell.send(f"\nconfigure terminal\n")  # ouvre la configuration du switch
        wait(shell)
        shell.send(
            "no ip ssh filetransfer\n"
        )  # désactive le ssh filetransfer, certain modèle requière de le désactiver avant d'activer tftp
        wait(shell)
        shell.send("tftp client\n")
        wait(shell)
        shell.send(f"copy tftp flash {ip_tftp} {chemin_version} primary\n")
        wait(shell)
        shell.send("yes\n")
        wait(shell)
        shell.send("ip ssh filetransfer\n")
        wait(shell)
        shell.send("no tftp client")
        wait(shell)
        time.sleep(1)
        tampon += shell.recv(65535).decode()
    return tampon


# Exécution principale avec multithreading
with ThreadPoolExecutor(max_threads) as executor:
    futures = {executor.submit(hote, host): host for host in hosts}
    for future in as_completed(futures):
        host = futures[future]
        try:
            future.result()  # Attendre que le thread se termine
        except Exception as e:
            print(f"Erreur avec l'hôte {host["ip"]} : {e}")

print("Traitement terminé pour tous les hôtes.")
