# High-Impact Feature Ideas & Future Enhancements

## 1. Multi-Chapter Context & Memory System
- **Chapter Capsule Memory:** Automatically generate a ~150 word "capsule summary" after completing each chapter. Inject previous chapter capsules into the prompt context for subsequent chapters.
- **Global Character Timeline & Lorebook:** Track key character state changes (injuries, relationship updates, inventory items) in a structured vector/JSON store to eliminate narrative inconsistencies across long novels.

## 2. Multi-Voice Audio & TTS Enhancements
- **Multi-Voice Dialogue Narration:** Assign unique TTS speaker profiles to each character in the project cast (e.g. narrator voice for prose, distinct male/female voice models for character dialogue).
- **Audiobook Exporter:** Merge generated beat audio clips into full chapter `.mp3` / `.m4b` files with background ambience/music tracks.

## 3. Image Generation & Visual Storyboarding
- **Consistent Character Ref Images:** Support reference image embedding (LoRA/ControlNet/IP-Adapter prompts) to maintain character visual consistency across generated chapter illustrations.
- **Interactive Storyboard Viewer:** Add a visual grid UI to view generated chapter scenes alongside their corresponding prose beats.

## 4. Export & Multi-Format Publishing
- **One-Click eBook Exporter:** Export complete novels to EPUB, PDF, and clean Markdown with embedded chapter images and table of contents.
- **Interactive Branching Choices:** Allow users to branch plot outlines at any chapter/beat ("What-if" scenario generator) and manage parallel storylines.

## 5. UI / UX Polish & Monitoring
- **Real-Time Token & Generation Metrics Dashboard:** Display token generation speed (tokens/sec), VRAM usage, and estimated cost per chapter in the UI.
- **Dark/Light Theme Customization & Mobile Layout:** Make the single-page frontend responsive for mobile and tablet reading/editing.
