import { handleUpload } from "@vercel/blob/client";
import { E } from "./_lib.js";
export default async function handler(req, res) {
  try {
    const json = await handleUpload({
      body: req.body, request: req,
      onBeforeGenerateToken: async (_path, clientPayload) => {
        if (!E("APP_PIN") || clientPayload !== E("APP_PIN")) throw new Error("PIN galat hai");
        return { allowedContentTypes: ["video/*", "audio/*", "image/*"], maximumSizeInBytes: 600 * 1024 * 1024, addRandomSuffix: true };
      },
      onUploadCompleted: async () => {},
    });
    res.json(json);
  } catch (e) { res.status(400).json({ error: e.message }); }
}
