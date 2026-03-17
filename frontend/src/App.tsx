import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/common/Layout';
import Dashboard from './pages/Dashboard';
import Squad from './pages/Squad';
import PlayerDetailPage from './pages/PlayerDetail';
import Tactics from './pages/Tactics';
import MatchDay from './pages/MatchDay';
import Training from './pages/Training';
import Transfers from './pages/Transfers';
import LeagueTable from './pages/LeagueTable';
import Analytics from './pages/Analytics';
import News from './pages/News';
import SaveManager from './pages/SaveManager';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SaveManager />} />
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/squad" element={<Squad />} />
          <Route path="/squad/:playerId" element={<PlayerDetailPage />} />
          <Route path="/tactics" element={<Tactics />} />
          <Route path="/match" element={<MatchDay />} />
          <Route path="/training" element={<Training />} />
          <Route path="/transfers" element={<Transfers />} />
          <Route path="/table" element={<LeagueTable />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/news" element={<News />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
