// Loads node-backend/.env into process.env. Imported first (before db.js /
// jsonStore.js) so USE_MONGO/DATA_DIR etc. are set before those modules read
// them at top level -- no more manual $env: exports needed each session.
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

try {
  process.loadEnvFile(path.resolve(__dirname, "../.env"));
} catch {
  // .env not present yet (fresh checkout before `cp .env.example .env`) -- fall back to shell env
}
