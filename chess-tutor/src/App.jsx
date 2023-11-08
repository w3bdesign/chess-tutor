import { useState } from "react";

import ChessBoard from "./components/ChessBoard";
import MoveHistory from "./components/MoveHistory";

import "./App.css";
import "@chrisoakman/chessboard2/dist/chessboard2.min.css";

function App() {
  const [movePairs, setMovePairs] = useState([]);

  return (
    <>
      <div className="flex flex-col p-2">
        <div className="shadow border bg-white rounded w-full min-w-[25rem]">
          <h1 className="text-2xl font-bold p-4">Chess Tutor</h1>
        </div>
      </div>
      <div className="flex flex-col p-2">
        <ChessBoard setMovePairs={setMovePairs} />
        <MoveHistory movePairs={movePairs} />
      </div>
    </>
  );
}

export default App;
