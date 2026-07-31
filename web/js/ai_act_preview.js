import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

app.registerExtension({
    name: "AIAct.UniversalSaverPreview",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // On cible uniquement notre nœud de sauvegarde
        if (nodeData.name !== "UniversalAIActSaver") return;

        // On sauvegarde le comportement d'origine s'il existe
        const onExecuted = nodeType.prototype.onExecuted;

        // On surcharge le handler d'exécution
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);

            // Nettoyage des anciens widgets de prévisualisation sur ce nœud ('this' est l'instance du nœud)
            if (this.widgets) {
                const customWidgets = this.widgets.filter(w => w.name === "ai_act_preview_widget");
                for (const w of customWidgets) {
                    if (w.element && w.element.parentNode) {
                        w.element.parentNode.removeChild(w.element);
                    }
                    const idx = this.widgets.indexOf(w);
                    if (idx !== -1) this.widgets.splice(idx, 1);
                }
            }

            // 1. LECTEUR VIDÉO (Flux 'gifs')
            if (message?.gifs && message.gifs.length > 0) {
                const item = message.gifs[0];
                const url = api.apiURL(`/view?filename=${encodeURIComponent(item.filename)}&type=${item.type}&subfolder=${encodeURIComponent(item.subfolder || "")}`);

                const container = document.createElement("div");
                container.style.width = "100%";
                container.style.padding = "4px";
                container.style.boxSizing = "border-box";

                const video = document.createElement("video");
                video.src = url;
                video.controls = true;
                video.autoplay = true;
                video.loop = true;
                video.muted = false;
                video.style.width = "100%";
                video.style.borderRadius = "6px";

                container.appendChild(video);

                this.addDOMWidget("ai_act_preview_widget", "preview", container, {
                    serialize: false,
                    hideOnZoom: false
                });

                // Redimensionnement automatique du nœud pour accueillir le lecteur
                this.setSize([this.size[0], Math.max(this.size[1], 380)]);
            }

            // 2. LECTEUR AUDIO (Flux 'audio')
            if (message?.audio && message.audio.length > 0) {
                const item = message.audio[0];
                const url = api.apiURL(`/view?filename=${encodeURIComponent(item.filename)}&type=${item.type}&subfolder=${encodeURIComponent(item.subfolder || "")}`);

                const container = document.createElement("div");
                container.style.width = "100%";
                container.style.padding = "6px";
                container.style.boxSizing = "border-box";

                const audio = document.createElement("audio");
                audio.src = url;
                audio.controls = true;
                audio.autoplay = false;
                audio.style.width = "100%";

                container.appendChild(audio);

                this.addDOMWidget("ai_act_preview_widget", "preview", container, {
                    serialize: false,
                    hideOnZoom: false
                });

                this.setSize([this.size[0], Math.max(this.size[1], 200)]);
            }
        };
    }
});