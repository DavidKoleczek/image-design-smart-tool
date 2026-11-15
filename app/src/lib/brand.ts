/** The app's name, as its windows, titles, and wordmark show it; the tool and its server keep their own. */
export const APP_NAME = "Image Design Smart Tool";

/** The app's name as its wordmark shows it, short enough to leave the top bar to the image in view. */
export const WORDMARK = "Image Design";

/** What the server filled into the view's meta tag `name`; nothing when it was served without one. */
function served(name: string): string | null {
  const content = document
    .querySelector<HTMLMetaElement>(`meta[name="${name}"]`)
    ?.content.trim();
  return content && !content.startsWith("{{") ? content : null;
}

/** The tool's version. */
export const VERSION = served("image-design-version");

/** The tool's repository, where its docs are. */
export const DOCUMENTATION = served("image-design-repository");
