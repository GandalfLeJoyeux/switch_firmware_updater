import paramiko
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime
import re
import os

"""
SCRIPT POUR SAUVEGARDER AUTOMATIQUEMENT LES CONFIGURATIONS EN COURS D'EXÉCUTION (running-config)
FONCTIONNE SEULEMENT SUR DES SWITCHES HP PROCURVE / ARUBA, MODÈLES TESTÉS : [2520, 2530, 2610, 2615, 2620, 2626, 2920, 2930F]
FORMAT DE FICHIER : YYYYMMDD/YYYYMMDD_HOSTNAME_IP.cfg
"""
# Configuration des identifiants (à remplacer par des variables d'environnement en production)
username = os.getenv("username")
password = os.getenv("password")


# Identifiants pour une utilisation manuel
# = ""
#password = ""

# Fichier source contenant la liste des IP des switches
ip_source = "sw_conf.txt"


# Création de la liste des hôtes à partir du fichier source
hosts = []
with open(ip_source, "r") as sw_conf:
    for line in sw_conf.readlines():
        hosts.append({"ip": line.strip()})

# Nombre maximum de connexions simultanées
max_threads = 100


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

        # Configuration initiale du switch
        initialisation(shell)

        # Ouverture de la session SFTP
        sftp = sftp_client.open_sftp()
        time.sleep(3)

        # Sauvegarde de la configuration
        backup_running(shell, sftp, host)

        # Enregistrement du rapport de sauvegarde
        with open("rapport.txt", "+a", encoding="utf-8") as file:
            file.write(f'{time.ctime()} | {host["hostname"]}({host["ip"]})\n')

    except TimeoutError as e:
        erreur(host, e)
        print(f"Timeout pour l'hôte {host["ip"]} : {e}")
    except Exception as e:
        erreur(host, e)
        print(f"Erreur avec l'hôte {host["ip"]} : {e}")
    finally:
        # Nettoyage des connexions
        client.close()
        sftp.close()


def initialisation(shell):
    """
    Configure le terminal et active le transfert SFTP
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
    wait(shell)
    wr_mem(shell)
    return


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


# Write memory commande, sauvegarde la configuration en cours.
def wr_mem(shell):
    shell.send("\nwrite memory\n")
    wait(shell)
    time.sleep(2)
    return


def get_running_config(shell):
    """
    Récupère la configuration complète du switch via la commande 'show running-config'

    Args:
        shell: Session shell SSH active

    Returns:
        str: Configuration complète du switch
    """
    tampon = ""
    try:
        # Envoie de la commande
        shell.send("show running-config\n")
        # Attend que le switch réponde
        wait(shell)
        # Pause pour laisser le temps au switch de générer toute la config
        time.sleep(5)
        # Lecture de la sortie jusqu'à ce qu'il n'y ait plus de données
        while shell.recv_ready():
            # Lecture par blocs de 65535 octets avec gestion des erreurs d'encodage
            tampon += shell.recv(65535).decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Erreur lors de l'exécution de 'show running-config': {e}")
    return tampon


def get_hostname(shell, host):
    """
    Extrait le nom d'hôte du switch depuis sa configuration

    Args:
        shell: Session shell SSH active
        host (dict): Dictionnaire contenant les informations du switch

    Returns:
        dict: Dictionnaire host mis à jour avec le hostname
    """
    # Récupération de la configuration complète
    tampon = get_running_config(shell)

    # Parcours ligne par ligne pour trouver le hostname
    for l in tampon.splitlines():
        if "hostname" in l:
            # Utilisation d'une regex pour extraire le hostname entre guillemets
            match = re.search(r'hostname\s+"([^"]+)"', l)
            if match:
                hostname = match.group(1)  # Extrait le hostname du groupe capturé
                host["hostname"] = hostname
                return host
        else:
            # Si le format n'est pas celui attendu
            host["hostname"] = None


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
