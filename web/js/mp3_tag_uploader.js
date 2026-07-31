import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

app.registerExtension({
    name: "AIAct.MP3TagUploader",
    async nodeCreated(node) {
        // Cibler uniquement notre nœud d'extraction de tags
        if (node.comfyClass === "MP3TagUploader_v5") {
            
            // Ajouter un bouton sur l'interface du nœud dans ComfyUI
            node.addWidget("button", "📁 Parcourir & Charger MP3", "upload", () => {
                
                // Créer un élément HTML 'input file' invisible
                const fileInput = document.createElement("input");
                fileInput.type = "file";
                fileInput.accept = "audio/*,.mp3,.wav,.ogg,.flac,.m4a";
                fileInput.style.display = "none";
                document.body.appendChild(fileInput);

                // Déclenché lorsque l'utilisateur sélectionne un fichier dans le navigateur
                fileInput.onchange = async (event) => {
                    const file = event.target.files[0];
                    if (!file) return;

                    // Préparer l'envoi du fichier vers l'API interne de ComfyUI
                    const formData = new FormData();
                    formData.append("image", file); // L'endpoint ComfyUI /upload/image prend en charge les médias
                    formData.append("overwrite", "true");
                    formData.append("subfolder", "");
                    formData.append("type", "input");

                    try {
                        const response = await api.fetchApi("/upload/image", {
                            method: "POST",
                            body: formData,
                        });

                        if (response.status === 200) {
                            const data = await response.json();
                            
                            // Mettre à jour le champ 'audio_file_name' avec le nom du fichier transféré
                            const widget = node.widgets.find((w) => w.name === "audio_file_name");
                            if (widget) {
                                widget.value = data.name;
                                app.graph.setDirtyCanvas(true, true);
                            }
                        } else {
                            alert("Erreur lors de l'envoi du fichier à ComfyUI.");
                        }
                    } catch (error) {
                        console.error("Erreur d'upload :", error);
                        alert("Erreur lors du transfert : " + error.message);
                    } finally {
                        document.body.removeChild(fileInput);
                    }
                };

                // Ouvrir l'explorateur de fichiers local
                fileInput.click();
            });
        }
    }
});