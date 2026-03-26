import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
  }
}

const secretBytes = () =>
  new TextEncoder().encode(process.env.NEXTAUTH_SECRET ?? "change-me");

/** Create a plain HS256 JWS token using native Web Crypto (no extra deps). */
async function signHS256(payload: Record<string, unknown>): Promise<string> {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const body = Buffer.from(
    JSON.stringify({ ...payload, iat: Math.floor(Date.now() / 1000) })
  ).toString("base64url");
  const data = `${header}.${body}`;

  const key = await crypto.subtle.importKey(
    "raw",
    secretBytes(),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data));
  return `${data}.${Buffer.from(sig).toString("base64url")}`;
}

/** Verify and decode an HS256 JWS token. Returns null if invalid. */
async function verifyHS256(token: string): Promise<Record<string, unknown> | null> {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [header, body, sig] = parts;
  const key = await crypto.subtle.importKey(
    "raw",
    secretBytes(),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  const valid = await crypto.subtle.verify(
    "HMAC",
    key,
    Buffer.from(sig, "base64url"),
    new TextEncoder().encode(`${header}.${body}`)
  );
  if (!valid) return null;
  return JSON.parse(Buffer.from(body, "base64url").toString());
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      authorize: async (credentials) => {
        const email = credentials?.email as string | undefined;
        if (!email || !email.includes("@")) return null;
        return { id: email, email, name: email.split("@")[0] };
      },
    }),
  ],
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  jwt: {
    encode: async ({ token }) =>
      signHS256(token as Record<string, unknown>),
    decode: async ({ token }) => {
      if (!token) return null;
      return verifyHS256(token);
    },
  },
  callbacks: {
    jwt: ({ token, user }) => {
      if (user) {
        token.sub = user.email ?? user.id;
        token.email = user.email;
        token.name = user.name;
        token.picture = user.image ?? null;
      }
      return token;
    },
    session: async ({ session, token }) => ({
      ...session,
      accessToken: await signHS256(token as Record<string, unknown>),
    }),
  },
});
