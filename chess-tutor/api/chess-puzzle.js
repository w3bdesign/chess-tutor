export const config = {
  runtime: "edge",
};

export default async function handler() {
  const rapidApiKey = process.env.RAPID_API_KEY;

  if (!rapidApiKey) {
    return new Response(
      JSON.stringify({ message: "API key is not configured" }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }
    );
  }

  try {
    const response = await fetch("https://chess-puzzles.p.rapidapi.com/", {
      method: "GET",
      headers: {
        "x-rapidapi-key": rapidApiKey,
        "x-rapidapi-host": "chess-puzzles.p.rapidapi.com",
      },
    });

    if (!response.ok) {
      throw new Error("Failed to fetch puzzle");
    }

    const data = await response.json();
    const puzzleData = data.puzzles[0];

    return new Response(
      JSON.stringify({
        id: puzzleData.puzzleid,
        fen: puzzleData.fen,
        solution: puzzleData.moves,
        rating: puzzleData.rating,
        themes: puzzleData.themes,
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }
    );
  } catch (error) {
    console.error("Error fetching puzzle:", error);
    return new Response(JSON.stringify({ message: "Error fetching puzzle" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}
