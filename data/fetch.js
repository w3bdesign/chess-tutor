const axios = require('axios');
const FormData = require('form-data');

async function fetchRandomChessPuzzle() {
  const url = 'https://lichess.org/training/complete/mix/jOszH';
  
  const formData = new FormData();
  formData.append('win', 'false');
  formData.append('rated', 'true');

  const config = {
    method: 'post',
    url: url,
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
      'Cookie': 'lila2=9bcbd579476a85bf5b13640b104d7d2b4d80f5ae-sid=DDpWTgfOFtnXxFHmmxABYK&bg=light',
      'authority': 'lichess.org',
      'accept': 'application/web.lichess+json',
      'accept-language': 'en-US,en;q=0.9',
      'cache-control': 'max-age=0',
      'origin': 'https://lichess.org',
      'referer': 'https://lichess.org/training/mix',
      'sec-ch-ua': '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
      'sec-ch-ua-mobile': '?0',
      'sec-ch-ua-platform': '"Windows"',
      'sec-fetch-dest': 'empty',
      'sec-fetch-mode': 'cors',
      'sec-fetch-site': 'same-origin',
      'x-requested-with': 'XMLHttpRequest',
      ...formData.getHeaders()
    },
    data: formData
  };

  try {
    const response = await axios(config);
    console.log('Puzzle data:', response.data);
    return response.data;
  } catch (error) {
    console.error('Error fetching puzzle:', error);
    throw error;
  }
}

// Usage
fetchRandomChessPuzzle()
  .then(puzzleData => {
    // Process the puzzle data here
  })
  .catch(error => {
    // Handle any errors
  });