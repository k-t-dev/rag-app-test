import "./globals.css";

export const metadata = {
  title: "Nail Knowledge RAG",
  description: "RBAC/ABAC対応 社内マニュアル検索AI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}

