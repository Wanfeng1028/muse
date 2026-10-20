import { loadFont as loadLocalFont } from "@remotion/fonts"
import { loadFont as loadGoogleFont } from "@remotion/google-fonts/HankenGrotesk"
import { staticFile } from "remotion"

// PLACEHOLDER FACE. Swap for the brand's fonts. Google fonts: import the family from @remotion/google-fonts
// (it blocks rendering until loaded). Local files: list them in LOCAL_FACES (public/fonts/...); @remotion/fonts
// wraps each load in delayRender/continueRender and calls cancelRender if a file fails, so a missing font fails
// the render loudly instead of falling back to a system face.
const google = loadGoogleFont("normal", { weights: ["500", "600", "700", "800"], subsets: ["latin"] })

type LocalFace = { family: string; file: string; weight: string; style?: "normal" | "italic" }
const LOCAL_FACES: LocalFace[] = []

let localFacesRequested = false

export function loadLocalFaces(): void {
  if (localFacesRequested || typeof document === "undefined") return
  localFacesRequested = true
  LOCAL_FACES.forEach((face) => {
    void loadLocalFont({ family: face.family, url: staticFile(face.file), weight: face.weight, style: face.style ?? "normal" })
  })
}

export const font = {
  sans: `${google.fontFamily}, system-ui, sans-serif`,
} as const
