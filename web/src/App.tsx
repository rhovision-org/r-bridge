import { HashRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import Overview from "./routes/Overview";
import Bridge from "./routes/Bridge";
import Settings from "./routes/Settings";

export const RELAYER_ISSUE =
  "https://github.com/rhovision-org/rholo/issues/563";

export default function App() {
  return (
    <HashRouter>
      <div className="app">
        <header className="topbar">
          <Link to="/" className="brand">
            r-bridge
          </Link>
          <span className="badge">scaffold</span>
          <nav className="nav">
            <NavLink to="/" end>
              Overview
            </NavLink>
            <NavLink to="/bridge">Bridge</NavLink>
            <NavLink to="/settings">Settings</NavLink>
          </nav>
        </header>
        <main className="main">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/bridge" element={<Bridge />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
        <footer className="footer">
          <span>AGPL-3.0-only</span>
          <a href={RELAYER_ISSUE} target="_blank" rel="noreferrer">
            rholo relayer add-on proposal
          </a>
        </footer>
      </div>
    </HashRouter>
  );
}
