import { useEffect, useRef, useState } from "react";
import { Chessboard2 } from "@chrisoakman/chessboard2/dist/chessboard2.min.mjs";
import { Chess } from "chess.js";

import useStockfishEvaluation from "../hooks/useStockfishEvaluation";

function ChessBoard({ setMovePairs }) {
  const chessboardRef = useRef(null);
  const chessRef = useRef(new Chess());

  const [moveHistory, setMoveHistory] = useState([]);

  const {
    data: evaluation,
    isLoading,
    error,
  } = useStockfishEvaluation(chessRef.current.fen());

  console.log("Is loading?", isLoading);

  useEffect(() => {
    const pairs = [];
    for (let i = 0; i < moveHistory.length; i += 2) {
      pairs.push({
        white: moveHistory[i],
        black: moveHistory[i + 1] || null,
      });
    }
    setMovePairs(pairs);
  }, [moveHistory, setMovePairs]);

  useEffect(() => {
    const boardConfig = {
      draggable: true,
      position: "start",
      showNotation: true,
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
        //chessboardRef.current.destroy();
      }
    };
  }, []);

  return (
    <>
      <p className="text-lg p-4 mt-2 mb-4 font-semibold shadow border bg-white rounded w-full">
        {error ? error.message : evaluation}
        {isLoading && "Calculating ..."}
      </p>
      <div
        id="myBoard"
        className="shadow border bg-white rounded p-4 w-full min-w-[40rem] min-h-[35rem]"
      ></div>
    </>
  );
}

export default ChessBoard;
