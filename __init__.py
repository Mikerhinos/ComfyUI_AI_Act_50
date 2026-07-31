import os
import sys
import shutil
import subprocess
import tempfile
import folder_paths
import imageio_ffmpeg

def log_cyan(text, is_error=False):
    prefix = "[AI-Act Error]" if is_error else "[AI-Act]"
    color = "\033[91m" if is_error else "\033[96m"
    reset = "\033[0m"
    print(f"{color}{prefix} {text}{reset}")

def get_ffmpeg_cmd():
    """
    Récupère le chemin du binaire FFmpeg embarqué via imageio-ffmpeg.
    Si indisponible, bascule sur le FFmpeg du PATH système.
    """
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_exe and os.path.exists(ffmpeg_exe):
            return ffmpeg_exe
    except Exception as e:
        log_cyan(f"Avertissement imageio-ffmpeg: {e}")

    # Secours : vérification du PATH système
    if shutil.which("ffmpeg"):
        return "ffmpeg"

    return None


class MP3TagUploader_v5:
    """
    Nœud pour charger, convertir et injecter les métadonnées ID3 dans des fichiers MP3 / Audio.
    """
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "audio_file_name": ("STRING", {"default": "audio.mp3", "multiline": False}),
                "title": ("STRING", {"default": "", "multiline": False}),
                "author": ("STRING", {"default": "", "multiline": False}),
            },
            "optional": {
                "lyrics": ("STRING", {"default": "", "multiline": True}),
                "images": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("file_path",)
    FUNCTION = "process"
    OUTPUT_NODE = True
    CATEGORY = "AI Act / Audio"

    def process(self, audio_file_name, title, author, lyrics="", images=None):
        ffmpeg_bin = get_ffmpeg_cmd()
        if not ffmpeg_bin:
            log_cyan("Erreur : Aucun binaire FFmpeg disponible (imageio-ffmpeg ou système).", is_error=True)
            return {"ui": {}, "result": ("Erreur: FFmpeg introuvable",)}

        cwd = os.getcwd()
        comfy_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Emplacements de recherche du fichier audio
        search_paths = [
            folder_paths.get_input_directory(),
            folder_paths.get_output_directory(),
            folder_paths.get_temp_directory(),
            os.path.join(cwd, "input"),
            os.path.join(cwd, "output"),
            os.path.join(cwd, "temp"),
            os.path.join(comfy_root, "input"),
            os.path.join(comfy_root, "output"),
            cwd,
        ]

        source_audio_path = None
        for p in search_paths:
            if not p:
                continue
            candidate = os.path.join(p, audio_file_name)
            if os.path.exists(candidate):
                source_audio_path = candidate
                break

        if not source_audio_path:
            log_cyan(f"Fichier audio introuvable : {audio_file_name}", is_error=True)
            return {"ui": {}, "result": (f"Erreur: Fichier {audio_file_name} introuvable",)}

        output_dir = folder_paths.get_output_directory()
        out_mp3_name = f"tagged_{os.path.splitext(audio_file_name)[0]}.mp3"
        out_mp3_path = os.path.join(output_dir, out_mp3_name)

        # Génération de la commande FFmpeg
        ffmpeg_cmd = [
            ffmpeg_bin, '-y', '-v', 'error',
            '-i', source_audio_path,
            '-acodec', 'libmp3lame', '-b:a', '192k',
            '-metadata', f'title={title}',
            '-metadata', f'artist={author}',
            '-metadata', f'album_artist=AI generated media',
        ]
        if lyrics:
            ffmpeg_cmd.extend([
                '-metadata', f'lyrics={lyrics}',
                '-metadata', f'comment={lyrics}'
            ])
        ffmpeg_cmd.append(out_mp3_path)

        try:
            log_cyan(f"Utilisation du binaire FFmpeg : {ffmpeg_bin}")
            subprocess.run(ffmpeg_cmd, check=True)
            log_cyan(f"Fichier généré avec succès : {out_mp3_path}")
        except Exception as e:
            log_cyan(f"Erreur lors de la conversion FFmpeg : {e}", is_error=True)
            return {"ui": {}, "result": (f"Erreur FFmpeg: {e}",)}

        return {"ui": {"text": [out_mp3_name]}, "result": (out_mp3_path,)}


# Déclaration du dossier web pour charger les extensions JS
WEB_DIRECTORY = "./web"

NODE_CLASS_MAPPINGS = {
    "MP3TagUploader_v5": MP3TagUploader_v5
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MP3TagUploader_v5": "MP3 Tag Uploader / Loader (v5)"
}