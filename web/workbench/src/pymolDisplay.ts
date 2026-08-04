const MANAGED_REGION_STICK_COMMAND =
  /^\s*show\s+sticks?\s*,\s*ed_region_[ABC]\s*$/i;

export function pymolDisplayPml(
  pml: string,
  stageNumber: 1 | 2,
): string {
  void stageNumber;
  return pml
    .split(/\r?\n/)
    .filter((line) => !MANAGED_REGION_STICK_COMMAND.test(line))
    .join("\n");
}
