export function splitAgentLabel(label: string) {
  const [name, ...modelParts] = label.split(" - ")
  return {
    name: name.trim(),
    model: modelParts.join(" - ").trim(),
  }
}

export function agentInitials(label: string) {
  const { name } = splitAgentLabel(label)
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase()
}
