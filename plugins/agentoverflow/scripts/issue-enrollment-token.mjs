import { createHmac, randomBytes } from "node:crypto";

const secret = process.env.AGENTOVERFLOW_REGISTRATION_INVITE_SECRET?.trim() || "";
if (secret.length < 32) {
  throw new Error(
    "Set AGENTOVERFLOW_REGISTRATION_INVITE_SECRET to the production invite secret."
  );
}

const requestedHours = Number(process.argv[2] || 24);
if (!Number.isFinite(requestedHours) || requestedHours <= 0 || requestedHours > 720) {
  throw new Error("Invite lifetime must be between 1 and 720 hours.");
}

const inviteId = randomBytes(18).toString("base64url");
const expiresAt = Math.floor(Date.now() / 1000) + Math.floor(requestedHours * 3600);
const payload = `invite:v1:${inviteId}:${expiresAt}`;
const signature = createHmac("sha256", secret).update(payload).digest("base64url");
const enrollmentToken = `${Buffer.from(payload).toString("base64url")}.${signature}`;

process.stdout.write(
  `${JSON.stringify(
    {
      enrollment_token: enrollmentToken,
      expires_at: new Date(expiresAt * 1000).toISOString(),
      single_use: true,
    },
    null,
    2
  )}\n`
);
