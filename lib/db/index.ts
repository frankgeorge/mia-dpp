import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

const connectionString = process.env.DATABASE_URL!;

// Single connection instance — reused across warm Vercel instances
const client = postgres(connectionString, { max: 5, ssl: "require" });

export const db = drizzle(client, { schema });
