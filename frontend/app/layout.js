import "./globals.css";

export const metadata = {
  title: "LifeOps",
  description: "Multi-agent productivity orchestrator",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}