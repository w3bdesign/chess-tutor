import { useEffect, useRef, useState } from "react";
import { Chessboard2 } from "@chrisoakman/chessboard2/dist/chessboard2.min.mjs";
import { Chess } from "chess.js";
import useStockfishEvaluation from "./hooks/useStockfishEvaluation";

import MoveHistory from "./components/MoveHistory";

import "./App.css";
import "@chrisoakman/chessboard2/dist/chessboard2.min.css";

function App() {
  const chessboardRef = useRef(null);
  const chessRef = useRef(new Chess());

  const [moveHistory, setMoveHistory] = useState([]);
  const [movePairs, setMovePairs] = useState([]);

  const {
    data: evaluation,
    isError,
    error,
  } = useStockfishEvaluation(chessRef.current.fen());

  useEffect(() => {
    const pairs = [];
    for (let i = 0; i < moveHistory.length; i += 2) {
      pairs.push({
        white: moveHistory[i],
        black: moveHistory[i + 1] || null,
      });
    }
    setMovePairs(pairs);
  }, [moveHistory]);

  useEffect(() => {
    const boardConfig = {
      draggable: true,
      position: "start",
      onDrop: ({ source, target }) => {
        const move = chessRef.current.move({
          from: source,
          to: target,
          promotion: "q",
        });

        if (move === null) return "snapback";

        chessboardRef.current.position(chessRef.current.fen());
        setMoveHistory(chessRef.current.history({ verbose: true }));
      },
    };

    chessboardRef.current = Chessboard2("myBoard", boardConfig);

    return () => {
      if (chessboardRef.current) {
        chessboardRef.current.destroy();
      }
    };
  }, []);

  return (
    <>
      <div className="flex flex-col p-2">
        <div className="shadow border bg-white rounded w-full min-w-[25rem]">
          <h1 className="text-2xl font-bold p-4">Chess Tutor</h1>
          <p className="text-lg p-4 font-semibold">
            Stockfish evaluation: {isError ? error.message : evaluation}
          </p>
        </div>
      </div>
      <div className="flex flex-col p-2">
        <div
          id="myBoard"
          className="shadow border bg-white rounded p-4 w-full min-w-[40rem] min-h-[35rem]"
        ></div>
        <MoveHistory movePairs={movePairs} />
      </div>
    </>
  );
}

export default App;
