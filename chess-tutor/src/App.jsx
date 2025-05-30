import React, { useEffect } from "react";
import {
  BrowserRouter as Router,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import ChessBoard from "./components/ChessBoard";
import MoveHistory from "./components/MoveHistory";
import Navbar from "./components/Navbar";
import PuzzlePage from "./Puzzles";

import { useChessStore } from "./stores/useChessStore";

import "./App.css";
import "@chrisoakman/chessboard2/dist/chessboard2.min.css";

function AppContent() {
  const location = useLocation();
  const resetGame = useChessStore((state) => state.resetGame);

  useEffect(() => {
    resetGame();
  }, [location.pathname, resetGame]);

  return (
    <div className="container mx-auto p-4">
      <Navbar />
      <Routes>
        <Route
          path="/"
          element={
            <>
              <div className="shadow border bg-white rounded w-full mb-4">
                <h1 className="text-2xl font-bold p-4">Chess Tutor</h1>
              </div>
              <div className="flex flex-col lg:flex-row gap-4">
                <div className="lg:w-2/3">
                  <ChessBoard />
                  <button
                    onClick={resetGame}
                    className="mt-4 bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
                  >
                    Reset Game
                  </button>
                </div>
                <div className="lg:w-1/3">
                  <MoveHistory />
                </div>
              </div>
            </>
          }
        />
        <Route path="/puzzles" element={<PuzzlePage />} />
      </Routes>
    </div>
  );
}

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}

export default App;
