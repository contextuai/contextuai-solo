import { useState } from "react";

export default function App() {
  const [count, setCount] = useState(0);

  return (
    <main
      style={{
        fontFamily: "system-ui, sans-serif",
        padding: "3rem",
        textAlign: "center",
      }}
    >
      <h1>Coder Web App</h1>
      <p>Edit <code>src/App.tsx</code> and save to hot-reload.</p>
      <button
        onClick={() => setCount((c) => c + 1)}
        style={{
          fontSize: "1.25rem",
          padding: "0.5rem 1.25rem",
          marginTop: "1rem",
          cursor: "pointer",
        }}
      >
        Count is {count}
      </button>
    </main>
  );
}
