import os
import sys
import re
import time
import json
import shutil
import subprocess
from pathlib import Path
import torch
import torchaudio
import numpy as np
from PIL import Image, PngImagePlugin
import imageio
import folder_paths

# ==============================================================================
# LOGGER CENTRALISÉ (SORTIE TERMINAL BLEU CIEL)
# ==============================================================================

def log_cyan(msg: str, is_error: bool = False):
    prefix = "[AI ACT NODE - ERREUR]" if is_error else "[AI ACT NODE]"
    print(f"\033[96m{prefix} {msg}\033[0m", flush=True)


def get_default_downloads_dir():
    try:
        downloads_path = Path.home() / "Downloads"
        if downloads_path.exists():
            return str(downloads_path)
    except Exception:
        pass
    return folder_paths.get_output_directory()


# Gestion sécurisée de Mutagen & ID3 Lyrics
try:
    import mutagen
    from mutagen.easyid3 import EasyID3
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, USLT, COMM, ID3NoHeaderError
    MUTAGEN_LOADED = True
except ImportError:
    mutagen = None
    EasyID3 = None
    MP3 = None
    ID3 = None
    USLT = None
    COMM = None
    ID3NoHeaderError = Exception
    MUTAGEN_LOADED = False


# ==============================================================================
# 1. LECTEUR ET EXTRACTEUR DE TAGS AUDIO / MP3
# ==============================================================================

class MP3TagUploader_v5:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "audio_file_name": ("STRING", {"default": "", "placeholder": "Nom du fichier MP3 (ex: output.mp3)..."}),
                "audio": ("AUDIO",),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING") 
    RETURN_NAMES = ("author", "lyrics", "title", "filename_safe")
    FUNCTION = "extract"
    CATEGORY = "audio/tags"

    def format_title_for_filename(self, title):
        if not title or title in ["Inconnu", "title", "Erreur lecture"]:
            return "audio_file_output"
        
        safe_title = title[:30]
        safe_title = safe_title.replace(" ", "_")
        safe_title = re.sub(r'[\\/:*?"<>|]', '', safe_title)
        safe_title = re.sub(r'__+', '_', safe_title)
        safe_title = safe_title.strip('_')
        return safe_title

    def extract(self, audio_file_name="", audio=None):
        if not MUTAGEN_LOADED:
            log_cyan("Échec extraction MP3 : dépendance 'mutagen' manquante.", is_error=True)
            return ("ERREUR: Dépendance manquante", "Veuillez installer mutagen: pip install mutagen", "erreur_mutagen", "erreur")

        full_path = None

        # 1. Recherche via le dictionnaire AUDIO si un chemin y est attaché
        if audio is not None and isinstance(audio, dict):
            if "path" in audio and os.path.exists(audio["path"]):
                full_path = audio["path"]
            elif "filename" in audio:
                audio_file_name = audio["filename"]

        # 2. Recherche du fichier sur le disque
        if not full_path and audio_file_name:
            cwd = os.getcwd()
            comfy_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if "comfy.git" in comfy_root:
                 comfy_root = os.path.dirname(comfy_root)

            search_paths = [
                folder_paths.get_input_directory(),
                folder_paths.get_output_directory(),
                folder_paths.get_temp_directory(),
                os.path.join(cwd, "output"),
                os.path.join(cwd, "input"),
                os.path.join(cwd, "temp"),
                os.path.join(comfy_root, "output"),
                os.path.join(comfy_root, "input"),
                cwd,
            ]
            
            for path in search_paths:
                potential_path = os.path.join(path, audio_file_name)
                if os.path.exists(potential_path):
                    full_path = potential_path
                    break
        
        if not full_path or not os.path.exists(full_path):
             log_cyan(f"Échec extraction MP3 : fichier introuvable ('{audio_file_name}').", is_error=True)
             return ("Erreur: Fichier introuvable", "", "Fichier introuvable", "erreur_chemin")
        
        author = "Inconnu"
        title = "Inconnu"
        lyrics_text = ""

        try:
            # Extraction des métadonnées standards (Artist, Title)
            audio_obj = mutagen.File(full_path, easy=True)
            if audio_obj is not None:
                author = audio_obj.get("artist", ["Inconnu"])[0]
                title = audio_obj.get("title", ["Inconnu"])[0] 

            # Extraction des paroles / texte TTS via ID3 USLT / COMM
            if ID3:
                try:
                    id3_tags = ID3(full_path)
                    uslt_frames = id3_tags.getall("USLT")
                    if uslt_frames:
                        lyrics_text = str(uslt_frames[0].text)
                    else:
                        comm_frames = id3_tags.getall("COMM")
                        if comm_frames:
                            lyrics_text = str(comm_frames[0].text)
                except Exception as e_id3:
                    log_cyan(f"Information : Pas de tag ID3 USLT/COMM lisible dans '{audio_file_name}': {e_id3}")

            filename_safe_title = self.format_title_for_filename(title)
            log_cyan(f"✅ Tags lus ('{os.path.basename(full_path)}') -> Auteur: '{author}' | Paroles: {len(lyrics_text)} car. | Titre: '{title}'")

        except Exception as e:
            log_cyan(f"Erreur de lecture des tags MP3 : {e}", is_error=True)
            author = "Erreur lecture"
            title = "Erreur lecture"
            lyrics_text = ""
            filename_safe_title = "erreur_lecture_safe"
        
        return (author, lyrics_text, title, filename_safe_title)


# ==============================================================================
# 2. NŒUD UNIVERSAL SAVER
# ==============================================================================

class UniversalAIActSaver:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "filename": ("STRING", {"default": "AI_Act_Output"}),
                "author": ("STRING", {"default": "AI Generator"}),
                "title": ("STRING", {"default": "AI Generated Media"}),
                "ai_label": ("STRING", {"default": "Généré par IA"}),
                "save_path": ("STRING", {"default": get_default_downloads_dir()}),
                "export_mode": ([
                    "Auto-détection",
                    "Image JPG (Visible dans Windows)",
                    "Image PNG",
                    "Vidéo MP4",
                    "Audio MP3"
                ], {"default": "Auto-détection"}),
            },
            "optional": {
                "images": ("IMAGE",),
                "audio": ("AUDIO",),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 1.0}),
                "lyrics": ("STRING", {"default": "", "multiline": True, "placeholder": "Collez ou connectez ici le texte/script TTS utilisé..."}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_path",)
    FUNCTION = "process"
    OUTPUT_NODE = True
    CATEGORY = "AI Act Compliance"

    def sanitize_filename(self, filename):
        return re.sub(r'[\\/:*?"<>|]', '_', filename).strip()

    def process(self, filename="AI_Act_Output", author="AI Generator", title="AI Generated Media", ai_label="Généré par IA", save_path="", export_mode="Auto-détection", images=None, audio=None, fps=24.0, lyrics="", prompt=None, extra_pnginfo=None):
        
        clean_name = self.sanitize_filename(filename)
        dest_dir = save_path.strip() if save_path else get_default_downloads_dir()
        
        if not os.path.exists(dest_dir):
            try:
                os.makedirs(dest_dir, exist_ok=True)
            except Exception as e:
                log_cyan(f"Impossible de créer le dossier de destination {dest_dir}: {e}", is_error=True)
                dest_dir = folder_paths.get_output_directory()

        target_type = export_mode
        if target_type == "Auto-détection":
            if audio is not None and images is None:
                target_type = "Audio MP3"
            elif images is not None and audio is not None:
                target_type = "Vidéo MP4"
            elif images is not None:
                if len(images) > 1:
                    target_type = "Vidéo MP4"
                else:
                    target_type = "Image JPG (Visible dans Windows)"
            else:
                log_cyan("Aucun flux d'entrée connecté.", is_error=True)
                return {"ui": {}, "result": ("Aucune entrée connectée",)}

        # ----------------------------------------------------------------------
        # CAS 1 : IMAGE (JPG / PNG)
        # ----------------------------------------------------------------------
        if "Image" in target_type:
            if images is None:
                log_cyan("Erreur : l'entrée 'images' est vide.", is_error=True)
                return {"ui": {}, "result": ("Erreur: Image manquante",)}

            is_jpg = "JPG" in target_type
            ext = "jpg" if is_jpg else "png"
            results = []
            saved_paths = []

            for idx, img_tensor in enumerate(images):
                img_np = (255. * img_tensor.cpu().numpy()).clip(0, 255).astype(np.uint8)
                pil_img = Image.fromarray(img_np)
                if is_jpg and pil_img.mode == "RGBA":
                    pil_img = pil_img.convert("RGB")

                exif = pil_img.getexif()
                exif[0x013B] = author
                exif[0x010E] = f"{ai_label} - EU AI Act Art. 50"
                exif[0x0131] = "ComfyUI AI Act Transparency Node"

                try:
                    exif[0x9C9D] = author.encode('utf-16-le')
                    exif[0x9C9B] = title.encode('utf-16-le')
                    exif[0x9C9C] = f"{ai_label} - EU AI Act Art. 50".encode('utf-16-le')
                except Exception as e_xp:
                    log_cyan(f"Erreur encodage XPAuthor: {e_xp}", is_error=True)

                exif_bytes = exif.tobytes()
                suffix = f"_{idx:04d}" if len(images) > 1 else ""
                final_file_path = os.path.join(dest_dir, f"{clean_name}{suffix}.{ext}")

                metadata = None
                if not is_jpg:
                    metadata = PngImagePlugin.PngInfo()
                    metadata.add_text("Author", author)
                    metadata.add_text("Artist", author)
                    metadata.add_text("Title", title)
                    metadata.add_text("Comment", f"{ai_label} - EU AI Act Art. 50")
                    if lyrics:
                        metadata.add_text("Description", lyrics)

                if is_jpg:
                    pil_img.save(final_file_path, format="JPEG", quality=95, exif=exif_bytes)
                else:
                    pil_img.save(final_file_path, format="PNG", pnginfo=metadata, exif=exif_bytes, compress_level=4)

                saved_paths.append(final_file_path)

                temp_preview = os.path.join(folder_paths.get_temp_directory(), f"prev_{int(time.time())}_{idx}.{ext}")
                if is_jpg:
                    pil_img.save(temp_preview, format="JPEG", quality=95, exif=exif_bytes)
                else:
                    pil_img.save(temp_preview, format="PNG", pnginfo=metadata, exif=exif_bytes, compress_level=4)

                results.append({"filename": os.path.basename(temp_preview), "subfolder": "", "type": "temp"})

            out_str = saved_paths[0] if len(saved_paths) == 1 else json.dumps(saved_paths)
            return {"ui": {"images": results}, "result": (out_str,)}

        # ----------------------------------------------------------------------
        # CAS 2 : AUDIO MP3
        # ----------------------------------------------------------------------
        elif "Audio" in target_type:
            if audio is None:
                log_cyan("Erreur : l'entrée 'audio' est vide.", is_error=True)
                return {"ui": {}, "result": ("Erreur: Audio manquant",)}

            waveform = audio.get("waveform") if isinstance(audio, dict) else audio
            sr = audio.get("sample_rate", 44100) if isinstance(audio, dict) else 44100

            waveform_save = waveform.clone().cpu()
            if waveform_save.dim() == 3:
                waveform_save = waveform_save[0]
            if waveform_save.dim() == 1:
                waveform_save = waveform_save.unsqueeze(0)
            if waveform_save.shape[0] > waveform_save.shape[1]:
                waveform_save = waveform_save.transpose(0, 1)

            temp_dir = folder_paths.get_temp_directory()
            timestamp_id = int(time.time())
            temp_wav = os.path.join(temp_dir, f"temp_{timestamp_id}.wav")
            final_mp3 = os.path.join(dest_dir, f"{clean_name}.mp3")
            temp_mp3_preview = os.path.join(temp_dir, f"prev_{timestamp_id}.mp3")

            torchaudio.save(temp_wav, waveform_save, sr, format="wav")

            def build_mp3(out_path):
                ffmpeg_cmd = [
                    'ffmpeg', '-y', '-v', 'error',
                    '-i', temp_wav,
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
                ffmpeg_cmd.append(out_path)
                subprocess.run(ffmpeg_cmd, check=True)

            build_mp3(final_mp3)
            build_mp3(temp_mp3_preview)

            if os.path.exists(temp_wav):
                os.unlink(temp_wav)

            if MUTAGEN_LOADED:
                for target_path in [final_mp3, temp_mp3_preview]:
                    try:
                        easy_audio = EasyID3(target_path)
                    except Exception:
                        file_obj = MP3(target_path)
                        if file_obj.tags is None:
                            file_obj.add_tags()
                            file_obj.save()
                        easy_audio = EasyID3(target_path)

                    easy_audio["title"] = title
                    easy_audio["artist"] = author
                    easy_audio.save(v2_version=3)

                    if lyrics and ID3:
                        try:
                            id3_tags = ID3(target_path)
                            id3_tags.add(USLT(encoding=3, lang='fra', desc='TTS Text', text=lyrics))
                            id3_tags.add(COMM(encoding=3, lang='fra', desc='TTS Prompt', text=lyrics))
                            id3_tags.save(v2_version=3)
                        except Exception as e_id3:
                            log_cyan(f"Erreur écriture ID3 USLT: {e_id3}", is_error=True)

            log_cyan(f"✅ Fichier Audio MP3 enregistré avec paroles/TTS ({len(lyrics)} car.) -> {final_mp3}")
            
            preview_res = {"filename": os.path.basename(temp_mp3_preview), "subfolder": "", "type": "temp", "format": "audio/mp3"}
            return {"ui": {"audio": [preview_res]}, "result": (final_mp3,)}

        # ----------------------------------------------------------------------
        # CAS 3 : VIDÉO MP4
        # ----------------------------------------------------------------------
        elif "Vidéo" in target_type:
            if images is None:
                log_cyan("Erreur : l'entrée 'images' est vide pour la vidéo.", is_error=True)
                return {"ui": {}, "result": ("Erreur: Images manquantes pour vidéo",)}

            frames = [(255. * img.cpu().numpy()).clip(0, 255).astype(np.uint8) for img in images]
            
            temp_dir = folder_paths.get_temp_directory()
            timestamp_id = int(time.time())
            final_mp4 = os.path.join(dest_dir, f"{clean_name}.mp4")
            temp_preview = os.path.join(temp_dir, f"prev_{timestamp_id}.mp4")

            ffmpeg_metadata = [
                '-metadata', f'artist={author}',
                '-metadata', f'title={title}',
                '-metadata', f'comment={lyrics if lyrics else f"{ai_label} - EU AI Act Art. 50"}',
                '-metadata', f'description={lyrics}',
                '-metadata', 'software=ComfyUI AI Act Transparency Node'
            ]

            if audio is not None:
                temp_raw_vid = os.path.join(temp_dir, f"temp_vid_{timestamp_id}.mp4")
                writer = imageio.get_writer(temp_raw_vid, fps=fps, codec='libx264')
                for frame in frames:
                    writer.append_data(frame)
                writer.close()

                waveform = audio.get("waveform") if isinstance(audio, dict) else audio
                sr = audio.get("sample_rate", 44100) if isinstance(audio, dict) else 44100

                waveform_save = waveform.clone().cpu()
                if waveform_save.dim() == 3:
                    waveform_save = waveform_save[0]
                if waveform_save.dim() == 1:
                    waveform_save = waveform_save.unsqueeze(0)
                if waveform_save.shape[0] > waveform_save.shape[1]:
                    waveform_save = waveform_save.transpose(0, 1)

                temp_aud_wav = os.path.join(temp_dir, f"temp_aud_{timestamp_id}.wav")
                torchaudio.save(temp_aud_wav, waveform_save, sr, format="wav")

                def combine_av(out_path):
                    cmd = [
                        'ffmpeg', '-y', '-v', 'error',
                        '-i', temp_raw_vid,
                        '-i', temp_aud_wav,
                        '-c:v', 'copy',
                        '-c:a', 'aac', '-b:a', '192k',
                        '-shortest'
                    ] + ffmpeg_metadata + [out_path]
                    subprocess.run(cmd, check=True)

                combine_av(final_mp4)
                combine_av(temp_preview)

                if os.path.exists(temp_raw_vid):
                    os.unlink(temp_raw_vid)
                if os.path.exists(temp_aud_wav):
                    os.unlink(temp_aud_wav)

                log_cyan(f"✅ Vidéo MP4 avec piste Audio & Métadonnées enregistrée -> {final_mp4}")

            else:
                writer = imageio.get_writer(final_mp4, fps=fps, codec='libx264', output_params=ffmpeg_metadata)
                for frame in frames:
                    writer.append_data(frame)
                writer.close()

                writer_prev = imageio.get_writer(temp_preview, fps=fps, codec='libx264', output_params=ffmpeg_metadata)
                for frame in frames:
                    writer_prev.append_data(frame)
                writer_prev.close()

                log_cyan(f"✅ Vidéo MP4 (muette) enregistrée -> {final_mp4}")
            
            preview_res = {"filename": os.path.basename(temp_preview), "subfolder": "", "type": "temp", "format": "video/mp4"}
            return {"ui": {"gifs": [preview_res]}, "result": (final_mp4,)}

        return {"ui": {}, "result": ("Erreur: Mode non supporté",)}


# ==============================================================================
# 3. MAPPINGS ET EXPORT
# ==============================================================================

WEB_DIRECTORY = "./web"

NODE_CLASS_MAPPINGS = {
    "MP3TagUploader_v5": MP3TagUploader_v5,
    "UniversalAIActSaver": UniversalAIActSaver,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MP3TagUploader_v5": "MP3 Tag Uploader / Loader (v5)",
    "UniversalAIActSaver": "Universal AI Act Saver (Image / Audio / Vidéo)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]