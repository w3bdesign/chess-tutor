import { useEffect } from "react";
import { Chessboard2 } from "/node_modules/@chrisoakman/chessboard2/dist/chessboard2.min.mjs";
import { Chess } from 'chess.js'

import "./App.css";
import "/node_modules/@chrisoakman/chessboard2/dist/chessboard2.min.css";

function App() {
  useEffect(() => {
    const board = Chessboard2("myBoard", "start");
    
    const chess = new Chess()
    while (!chess.isGameOver()) {
      const moves = chess.moves()
      const move = moves[Math.floor(Math.random() * moves.length)]
      chess.move(move)
    }
    console.log(chess.pgn())
  }, []);

  return (
    <>
      <div className="flex flex-col p-2">
        <div className="shadow border bg-white rounded w-full min-w-[25rem]">
          <h1 className="text-2xl font-bold p-4">Chess Tutor</h1>
        </div>
      </div>
      <div className="flex flex-col p-2">
        <div
          id="myBoard"
          className="shadow border bg-white rounded p-4 w-full min-w-[40rem] min-h-[35rem]"
        ></div>
      </div>
    </>
  );
}

export default App;
