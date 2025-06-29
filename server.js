const express = require('express');
const bodyParser = require('body-parser');
const crypto = require('crypto');
const app = express();
const PORT = process.env.PORT || 3000;

app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json());
app.use(express.static('public')); // for index.html

const htmlStore = {}; // In-memory store

// Serve index.html
app.get('/', (req, res) => {
  res.sendFile(__dirname + '/public/index.html');
});

// Submit HTML and generate ID
app.post('/html/preview', (req, res) => {
  const htmlCode = req.body.html_code;
  const id = crypto.randomBytes(4).toString('hex'); // 8-character ID
  htmlStore[id] = htmlCode;

  const url = `https://backend-drab-alpha-79.vercel.app/html/${id}`;
  res.redirect(url);
});

// Serve the rendered HTML
app.get('/html/:id', (req, res) => {
  const id = req.params.id;
  const htmlCode = htmlStore[id];
  if (!htmlCode) {
    return res.status(404).send('HTML Not Found');
  }
  res.send(htmlCode);
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
