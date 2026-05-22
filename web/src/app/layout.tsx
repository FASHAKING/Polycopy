import "../styles/globals.css";

export const metadata = {
  title: "Polycopy",
  description: "Polymarket copy-trading bot dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
