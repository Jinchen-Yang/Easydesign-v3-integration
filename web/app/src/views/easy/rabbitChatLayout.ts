type Viewport = { width: number; height: number; x: number; y: number };
type Pet = { x: number; y: number; size: number };

/** Keep the original pet outside the conversation, including at dragged positions. */
export function rabbitChatLayout(view: Viewport, saved: Pet) {
  const margin = 12;
  const gap = 32; // Leaves space for the existing ear sway and jumping animation.
  const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n));
  const left = view.x + margin,
    top = view.y + margin;
  const right = view.x + view.width - margin,
    bottom = view.y + view.height - margin;
  const width = Math.min(380, view.width - margin * 2);
  const height = Math.min(510, view.height - margin * 2);
  const size = Math.min(saved.size, view.height < 450 ? 96 : saved.size);
  const pet = {
    x: clamp(saved.x, left, right - size),
    y: clamp(saved.y, top, bottom - size),
    size,
  };
  const panel = { left: clamp(pet.x + size - width, left, right - width), top, width, height };
  const above = pet.y - gap - top;
  const below = bottom - pet.y - size - gap;

  if (above >= height) panel.top = pet.y - gap - height;
  else if (below >= height) panel.top = pet.y + size + gap;
  else if (pet.x - gap - left >= width) {
    panel.left = pet.x - gap - width;
    panel.top = clamp(pet.y + size / 2 - height / 2, top, bottom - height);
  } else if (right - pet.x - size - gap >= width) {
    panel.left = pet.x + size + gap;
    panel.top = clamp(pet.y + size / 2 - height / 2, top, bottom - height);
  } else if (Math.max(above, below) >= 300) {
    // A shorter scrollable conversation is preferable to covering the rabbit.
    panel.height = Math.min(height, Math.max(above, below));
    panel.top = above >= below ? pet.y - gap - panel.height : pet.y + size + gap;
  } else if (view.width >= 560) {
    // Short landscape viewport: temporarily pair the pet beside the conversation.
    pet.x = right - size;
    panel.width = Math.min(width, pet.x - gap - left);
    panel.left = pet.x - gap - panel.width;
  } else {
    // Narrow/keyboard viewport: reserve a pet area below the chat, without changing
    // the user's saved drag position. Closing the conversation restores that position.
    pet.y = bottom - size;
    panel.height = Math.min(height, Math.max(100, pet.y - gap - top));
    panel.top = pet.y - gap - panel.height;
  }
  return { pet, panel };
}
