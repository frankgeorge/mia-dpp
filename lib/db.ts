import postgres from "postgres";

const connectionString = process.env.DATABASE_URL!;

const sql = postgres(connectionString, {
  ssl: "require",
  max: 5,
  idle_timeout: 20,
  connect_timeout: 10,
});

export default sql;
